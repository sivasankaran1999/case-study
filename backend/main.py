import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from agent.graph import run_agent
from guardrails.nemo_gateway import sanitize_output
from config.settings import settings
from observability import (
    configure_logging,
    log_event,
    timer,
    metrics,
    bind_request_id,
    get_request_id,
)

load_dotenv()

configure_logging(settings.LOG_LEVEL)

# Optional LangSmith tracing when configured (per-node traces complement the
# structured logs + metrics emitted by the observability module).
_TRACING_ENABLED = bool(settings.LANGSMITH_API_KEY)
if _TRACING_ENABLED:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.LANGSMITH_API_KEY)
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.LANGSMITH_PROJECT)

log_event(
    "startup",
    service=settings.SERVICE_NAME,
    langsmith=_TRACING_ENABLED,
    fast_model=settings.LLM_FAST_MODEL,
    reasoning_model=settings.LLM_REASONING_MODEL,
)

app = FastAPI(
    title="PartSelect AI Agent",
    description="AI chat agent for Refrigerator and Dishwasher parts",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Assign a request id, time the request, and emit a structured access log.

    The request id propagates (via contextvar) into the agent and every LLM
    call, so all log lines for one turn share the same id. It's also echoed back
    in the ``X-Request-ID`` response header.
    """
    rid = bind_request_id(request.headers.get("X-Request-ID"))
    with timer() as t:
        try:
            response = await call_next(request)
        except Exception as exc:  # pragma: no cover - defensive
            metrics.inc("http_requests_total")
            metrics.inc("http_errors_total")
            log_event(
                "request_failed",
                level="error",
                method=request.method,
                path=request.url.path,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

    metrics.inc("http_requests_total")
    metrics.observe("http_latency_ms", t["ms"])
    if response.status_code >= 500:
        metrics.inc("http_errors_total")
    log_event(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        latency_ms=t["ms"],
    )
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": settings.SERVICE_NAME}


@app.get("/metrics")
def metrics_endpoint():
    """In-process counters + latency percentiles (requests, chat turns by
    intent, LLM calls, and token usage). For demo/local observability."""
    return metrics.snapshot()


@app.post("/chat")
def chat(request: dict):
    # Sync handler so FastAPI runs it in a threadpool — the agent calls
    # blocking LLM/scrape APIs, so this keeps requests from blocking each other.
    message = (request.get("message") or "").strip()
    image = request.get("image")
    # An image with no text is valid (e.g. just a photo of the model label).
    if not message and not image:
        return {
            "message": "Please enter a message.",
            "type": "text",
            "parts": [],
            "repair_steps": [],
            "repair_meta": None,
            "url": None,
            "confidence": 0.0,
        }

    metrics.inc("chat_turns_total")
    try:
        with timer() as t:
            result = run_agent(
                message=message,
                model_number=request.get("model_number"),
                conversation_history=request.get("conversation_history") or [],
                image=image,
            )
    except Exception as exc:
        metrics.inc("chat_errors_total")
        log_event(
            "chat_error",
            level="error",
            error=f"{type(exc).__name__}: {exc}",
            has_image=bool(image),
            has_model=bool(request.get("model_number")),
        )
        return {
            "message": (
                "Sorry — something went wrong while processing that. Please try "
                "again in a moment."
            ),
            "type": "error",
            "parts": [],
            "options": [],
            "repair_steps": [],
            "repair_meta": None,
            "url": None,
            "confidence": 0.0,
            "model_number": request.get("model_number") or None,
            "request_id": get_request_id(),
        }

    intent = result.get("intent") or "unknown"
    response_type = result.get("response_type", "text")
    confidence = float(result.get("confidence") or 0.0)
    parts = result.get("parts") or []

    metrics.inc(f"chat_intent.{intent}")
    metrics.inc(f"chat_response_type.{response_type}")
    metrics.observe("chat_latency_ms", t["ms"])
    log_event(
        "chat_turn",
        intent=intent,
        response_type=response_type,
        confidence=confidence,
        parts=len(parts),
        clarified=bool(result.get("clarify_question")),
        has_image=bool(image),
        has_model=bool(request.get("model_number")),
        msg_len=len(message),
        latency_ms=t["ms"],
    )

    return {
        "message": sanitize_output(result.get("response_message", "")),
        "type": response_type,
        "parts": parts,
        "options": result.get("options") or [],
        "repair_steps": result.get("repair_steps") or [],
        "repair_meta": result.get("repair_meta"),
        "url": result.get("order_url"),
        "confidence": confidence,
        "model_number": result.get("model_number") or None,
        "request_id": get_request_id(),
        "trace_id": result.get("trace_id"),
    }


# Lazily-built LangSmith client (only when tracing is configured). Reused across
# feedback calls so we don't re-init the SDK per request.
_ls_client = None


def _langsmith_client():
    global _ls_client
    if not _TRACING_ENABLED:
        return None
    if _ls_client is None:
        try:
            from langsmith import Client

            _ls_client = Client(api_key=settings.LANGSMITH_API_KEY)
        except Exception as exc:  # pragma: no cover - defensive
            log_event("feedback_client_error", level="warning", error=str(exc))
            _ls_client = None
    return _ls_client


@app.post("/feedback")
def feedback(request: dict):
    """Record a 👍/👎 on an agent answer.

    Sends the signal to three places: the LangSmith trace (so it's filterable in
    the dashboard and tied to the full router→executor→synthesizer run), the
    structured log stream, and the in-process metrics. Always succeeds for the
    UI — a LangSmith failure degrades to log + metrics, never blocks the user.
    """
    raw_score = request.get("score")
    # Accept 1/0, True/False, or "up"/"down".
    if raw_score in (1, "1", True, "up", "positive"):
        score = 1
    elif raw_score in (0, "0", False, "down", "negative"):
        score = 0
    else:
        return {"ok": False, "error": "score must be 1 (up) or 0 (down)"}

    trace_id = (request.get("trace_id") or "").strip() or None
    reason = (request.get("reason") or "").strip()[:500]
    comment = (request.get("comment") or "").strip()[:1000]
    query = (request.get("query") or "").strip()[:500]
    intent = (request.get("intent") or "").strip()[:64]

    metrics.inc("feedback_total")
    metrics.inc("feedback_positive" if score == 1 else "feedback_negative")
    if intent:
        metrics.inc(f"feedback_intent.{intent}.{'up' if score else 'down'}")

    log_event(
        "user_feedback",
        score=score,
        sentiment="up" if score == 1 else "down",
        trace_id=trace_id,
        reason=reason or None,
        comment=comment or None,
        intent=intent or None,
        query=query or None,
    )

    langsmith_logged = False
    client = _langsmith_client()
    if client and trace_id:
        try:
            # Combine the preset reason + any free text into the trace comment.
            full_comment = " — ".join(c for c in (reason, comment) if c) or None
            client.create_feedback(
                run_id=trace_id,
                key="user_thumbs",
                score=score,
                comment=full_comment,
            )
            langsmith_logged = True
        except Exception as exc:
            log_event("feedback_langsmith_error", level="warning", error=str(exc))

    return {"ok": True, "langsmith": langsmith_logged}
