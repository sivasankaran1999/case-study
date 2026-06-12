import math

import google.generativeai as genai
from tenacity import retry, wait_exponential, stop_after_attempt

from config.settings import settings

genai.configure(api_key=settings.GEMINI_API_KEY)


def _normalize(vec: list[float]) -> list[float]:
    """L2-normalize a vector.

    Google recommends normalizing gemini-embedding-001 outputs whenever a
    reduced output dimensionality (< 3072) is requested, so that cosine
    similarity behaves as expected.
    """
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding for a document chunk using gemini-embedding-001.
    Returns a 768-dimensional, L2-normalized vector.
    """
    result = genai.embed_content(
        model=settings.EMBEDDING_MODEL,
        content=text,
        task_type="retrieval_document",
        output_dimensionality=settings.EMBEDDING_DIMENSION,
    )
    return _normalize(result["embedding"])


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Batch-embed many document chunks in ONE API call.

    Indexing a single part page produces 7-14 chunks; embedding them one-by-one
    means 7-14 sequential network round-trips. The Gemini embedding endpoint
    accepts a list of contents and returns a list of vectors, so batching cuts
    that to a single round-trip — the main per-part latency win and the
    "handles scale" path (cost grows with API calls, not chunk count).

    Returns vectors in the SAME ORDER as ``texts``. Callers should fall back to
    per-chunk ``generate_embedding`` if this raises, so a batch hiccup never
    blocks indexing.
    """
    if not texts:
        return []
    result = genai.embed_content(
        model=settings.EMBEDDING_MODEL,
        content=texts,
        task_type="retrieval_document",
        output_dimensionality=settings.EMBEDDING_DIMENSION,
    )
    # Single-item batches can come back as a flat vector; normalize the shape.
    embeddings = result["embedding"]
    if embeddings and not isinstance(embeddings[0], (list, tuple)):
        embeddings = [embeddings]
    return [_normalize(vec) for vec in embeddings]


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_query_embedding(text: str) -> list[float]:
    """
    Generate an embedding for a search query.
    Uses the retrieval_query task type for better search accuracy.
    Returns a 768-dimensional, L2-normalized vector.
    """
    result = genai.embed_content(
        model=settings.EMBEDDING_MODEL,
        content=text,
        task_type="retrieval_query",
        output_dimensionality=settings.EMBEDDING_DIMENSION,
    )
    return _normalize(result["embedding"])
