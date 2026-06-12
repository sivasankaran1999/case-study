import time

from pinecone import Pinecone, ServerlessSpec

from config.settings import settings
from rag.embeddings import (
    generate_embedding,
    generate_embeddings,
    generate_query_embedding,
)

pc = Pinecone(api_key=settings.PINECONE_API_KEY)


def get_or_create_index():
    """
    Get the existing Pinecone index or create it if it doesn't exist.
    Uses a serverless spec for free-tier compatibility.
    """
    existing_indexes = [i.name for i in pc.list_indexes()]

    if settings.PINECONE_INDEX_NAME not in existing_indexes:
        pc.create_index(
            name=settings.PINECONE_INDEX_NAME,
            dimension=settings.EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        # Wait for the index to be ready before returning it
        while not pc.describe_index(settings.PINECONE_INDEX_NAME).status["ready"]:
            time.sleep(1)

    return pc.Index(settings.PINECONE_INDEX_NAME)


index = get_or_create_index()


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed many chunks, preferring a single batched call.

    Falls back to per-chunk embedding if the batch call fails or returns an
    unexpected count, so indexing is never blocked by a batch hiccup.
    """
    try:
        vecs = generate_embeddings(texts)
        if len(vecs) == len(texts):
            return vecs
    except Exception as e:  # noqa: BLE001
        print(f"Batch embed failed ({e}); falling back to per-chunk.")
    return [generate_embedding(t) for t in texts]


def upsert_documents(documents: list[dict], namespace: str):
    """
    Upsert a list of documents into Pinecone.
    Each document must have: id, text, metadata.
    Embeddings are batch-generated (one API call) then flushed in groups of 100.
    """
    embeddings = _embed_texts([doc["text"] for doc in documents])

    vectors = []
    for doc, embedding in zip(documents, embeddings):
        vectors.append(
            {
                "id": doc["id"],
                "values": embedding,
                "metadata": {"text": doc["text"], **doc.get("metadata", {})},
            }
        )
        if len(vectors) >= 100:
            index.upsert(vectors=vectors, namespace=namespace)
            vectors = []

    if vectors:
        index.upsert(vectors=vectors, namespace=namespace)


def query_index(query: str, namespace: str, top_k: int = None) -> list[dict]:
    """
    Query the Pinecone index with semantic search.
    Returns a list of matches with confidence scores.
    """
    top_k = top_k or settings.RAG_TOP_K
    query_embedding = generate_query_embedding(query)

    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True,
    )

    return [
        {
            "id": match.id,
            "confidence": match.score,
            "text": match.metadata.get("text", ""),
            "metadata": match.metadata,
        }
        for match in results.matches
    ]


def upsert_single(doc_id: str, text: str, metadata: dict, namespace: str):
    """
    Upsert a single document — used for self-healing RAG updates.
    """
    embedding = generate_embedding(text)
    index.upsert(
        vectors=[
            {
                "id": doc_id,
                "values": embedding,
                "metadata": {"text": text, **metadata},
            }
        ],
        namespace=namespace,
    )
