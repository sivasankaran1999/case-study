"""Tool: agentic discovery — plan, scrape, rank, and index on demand.

Exposes ``scraper.agentic_discovery.discover`` as an agent tool. It is NOT wired
into any default route: the live chat path is unchanged unless a caller opts in
(e.g. the executor's low-recall fallback, gated by ENABLE_AGENTIC_DISCOVERY, or
the standalone demo script). Indexing is additive — it only upserts new vectors
into the existing Pinecone namespaces.
"""

from scraper.agentic_discovery import discover
from config.settings import settings


def run(goal: str, signals: dict | None = None) -> dict:
    """Run a bounded agentic-discovery pass for ``goal``.

    Respects ENABLE_AGENTIC_DISCOVERY: when disabled, returns a no-op result so
    nothing scrapes unexpectedly in environments that haven't opted in.
    """
    if not settings.ENABLE_AGENTIC_DISCOVERY:
        return {
            "goal": goal,
            "skipped": True,
            "reason": "ENABLE_AGENTIC_DISCOVERY is off",
            "indexed_parts": [],
            "indexed_repairs": [],
            "models_cached": [],
        }
    return discover(goal, signals=signals or {})
