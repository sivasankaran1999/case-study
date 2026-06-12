"""Lightweight, dependency-free observability for the PartSelect agent.

Provides four things, all stdlib-only so it adds zero runtime risk:

1. Structured JSON logging (one JSON object per line) with a per-request id.
2. A request-id contextvar that propagates through the request -> agent -> LLM
   call chain so every log line for a turn shares the same id.
3. A ``timer()`` context manager for measuring wall-clock latency.
4. An in-process metrics registry (counters + latency percentiles) exposed via
   the ``/metrics`` endpoint, plus an LLM-call recorder that captures model,
   latency, and token usage.

LangSmith tracing (when ``LANGSMITH_API_KEY`` is set) complements this with full
per-node traces; see ``main.py`` and ``agent/graph.py``.
"""

from observability.core import (
    configure_logging,
    log_event,
    timer,
    metrics,
    new_request_id,
    bind_request_id,
    get_request_id,
    record_llm_call,
    usage_from_response,
)

__all__ = [
    "configure_logging",
    "log_event",
    "timer",
    "metrics",
    "new_request_id",
    "bind_request_id",
    "get_request_id",
    "record_llm_call",
    "usage_from_response",
]
