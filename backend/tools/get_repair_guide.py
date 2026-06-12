"""Tool: retrieve a structured repair guide for a described symptom."""

from rag.self_heal import lookup_repair_guide
from config.settings import settings


def run(symptom: str, top_k: int | None = None) -> list[dict]:
    return lookup_repair_guide(symptom, top_k=top_k or settings.RAG_TOP_K)
