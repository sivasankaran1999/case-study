"""Tool: semantic search over indexed parts + repair guides (Pinecone RAG)."""

from rag.pinecone_client import query_index
from config.settings import settings


def run(query: str, namespace: str | None = None, top_k: int | None = None) -> list[dict]:
    return query_index(
        query,
        namespace=namespace or settings.NAMESPACE_PARTS,
        top_k=top_k or settings.RAG_TOP_K,
    )
