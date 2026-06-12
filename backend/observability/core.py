"""Core observability primitives: structured logging, request-id propagation,
timing, and an in-process metrics registry. Stdlib only."""

import json
import logging
import sys
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# --------------------------------------------------------------------------- #
# Request id (shared across a single turn: request -> agent -> tools -> LLM)
# --------------------------------------------------------------------------- #
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def bind_request_id(rid: Optional[str]) -> str:
    """Set the current request id (generating one when absent). Returns it."""
    rid = (rid or "").strip() or new_request_id()
    _request_id.set(rid)
    return rid


def get_request_id() -> str:
    return _request_id.get()


# --------------------------------------------------------------------------- #
# Structured logging
# --------------------------------------------------------------------------- #
_LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}
_logger = logging.getLogger("partselect")


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Attach a single stdout handler that emits each record's message verbatim
    (we pre-serialize to JSON). Idempotent."""
    if not _logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(handler)
        _logger.propagate = False
    _logger.setLevel(_LEVELS.get(str(level).lower(), 20))
    return _logger


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    """Emit a single structured JSON log line for ``event``.

    ``None`` fields are dropped to keep lines compact. The current request id is
    always attached.
    """
    payload: Dict[str, Any] = {
        "ts": _now_iso(),
        "level": level.upper(),
        "event": event,
        "request_id": _request_id.get(),
    }
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    _logger.log(_LEVELS.get(level.lower(), 20), json.dumps(payload, default=str))


# --------------------------------------------------------------------------- #
# Timing
# --------------------------------------------------------------------------- #
@contextmanager
def timer():
    """Context manager yielding a dict whose ``ms`` key holds elapsed wall time.

    >>> with timer() as t:
    ...     do_work()
    >>> t["ms"]  # float milliseconds
    """
    box = {"ms": 0.0}
    start = time.perf_counter()
    try:
        yield box
    finally:
        box["ms"] = round((time.perf_counter() - start) * 1000, 1)


# --------------------------------------------------------------------------- #
# Metrics registry (thread-safe; FastAPI runs sync endpoints in a threadpool)
# --------------------------------------------------------------------------- #
def _summarize(samples) -> Dict[str, Any]:
    if not samples:
        return {"count": 0}
    ordered = sorted(samples)
    n = len(ordered)

    def pct(p: float):
        if n == 1:
            return ordered[0]
        idx = min(n - 1, int(round((p / 100.0) * (n - 1))))
        return ordered[idx]

    return {
        "count": n,
        "avg": round(sum(ordered) / n, 1),
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "min": ordered[0],
        "max": ordered[-1],
    }


class _Metrics:
    """Minimal in-memory counters + bounded latency samples.

    Not a replacement for Prometheus — it's a zero-dependency snapshot suitable
    for a single-process service and the demo ``/metrics`` endpoint.
    """

    def __init__(self, sample_cap: int = 1000):
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = defaultdict(float)
        self._latencies: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=sample_cap)
        )

    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, ms: float) -> None:
        with self._lock:
            self._latencies[name].append(ms)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            counters = dict(sorted(self._counters.items()))
            latency = {
                key: _summarize(list(vals))
                for key, vals in sorted(self._latencies.items())
            }
        return {"counters": counters, "latency_ms": latency}


metrics = _Metrics()


# --------------------------------------------------------------------------- #
# LLM call instrumentation
# --------------------------------------------------------------------------- #
def usage_from_response(resp: Any) -> Optional[Any]:
    """Best-effort extraction of the google-generativeai usage_metadata object."""
    return getattr(resp, "usage_metadata", None)


def record_llm_call(
    call: str,
    model: str,
    latency_ms: float,
    usage: Optional[Any] = None,
) -> None:
    """Record one LLM invocation: counts, latency, token usage, and a log line.

    ``call`` is a short label for the call site (e.g. "classify", "synthesize",
    "extract_json"). ``usage`` is the response's usage_metadata when available.
    """
    metrics.inc("llm_calls_total")
    metrics.inc(f"llm_calls.{call}")
    metrics.observe(f"llm_latency_ms.{call}", latency_ms)

    prompt_tokens = candidates_tokens = total_tokens = None
    if usage is not None:
        prompt_tokens = getattr(usage, "prompt_token_count", None)
        candidates_tokens = getattr(usage, "candidates_token_count", None)
        total_tokens = getattr(usage, "total_token_count", None)
        if total_tokens:
            metrics.inc("llm_tokens_total", float(total_tokens))
        if prompt_tokens:
            metrics.inc("llm_prompt_tokens_total", float(prompt_tokens))
        if candidates_tokens:
            metrics.inc("llm_candidates_tokens_total", float(candidates_tokens))

    log_event(
        "llm_call",
        call=call,
        model=model,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        candidates_tokens=candidates_tokens,
        total_tokens=total_tokens,
    )
