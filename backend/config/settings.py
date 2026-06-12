from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, List


class Settings(BaseSettings):
    # API Keys
    GEMINI_API_KEY: str
    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str = "partselect-parts"
    FIRECRAWL_API_KEY: str
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "partselect-agent"

    # Observability
    SERVICE_NAME: str = "partselect-agent"
    LOG_LEVEL: str = "INFO"

    # Agent Config
    MAX_ITERATIONS: int = 3
    CONFIDENCE_THRESHOLD: float = 0.8
    RAG_TOP_K: int = 5
    # Minimum semantic-search score for a part hit to be shown. Filler/vague
    # queries (e.g. "do you have other options") score ~0.62; real product or
    # symptom queries — after filler-stripping + category enrichment — score
    # ~0.66+. Below this floor we ask the user to clarify instead of surfacing
    # irrelevant parts.
    SEARCH_RELEVANCE_FLOOR: float = 0.66
    # Repair-guide matches at/above this score are trusted as-is. Only genuinely
    # weak matches below it trigger a live re-scrape (self-heal). Good symptom
    # matches score ~0.73-0.76, so the old CONFIDENCE_THRESHOLD (0.8) re-scraped
    # on EVERY query — pure wasted latency. This floor stops that.
    REPAIR_SELF_HEAL_FLOOR: float = 0.6

    # Two-tier LLM setup:
    #   FAST  -> high-volume, cheap work: structured extraction at index time,
    #            symptom tagging, intent routing.
    #   STRONG-> low-volume, quality-critical work: final answer synthesis,
    #            compatibility reasoning.
    LLM_FAST_MODEL: str = "models/gemini-2.5-flash"
    LLM_REASONING_MODEL: str = "models/gemini-2.5-pro"
    # Back-compat alias (extraction code referenced LLM_MODEL); points at FAST.
    LLM_MODEL: str = "models/gemini-2.5-flash"
    ENABLE_LLM_EXTRACTION: bool = True
    # Use the strong model to synthesize the final chat answer.
    ENABLE_LLM_SYNTHESIS: bool = True

    # Scrape/crawl breadth controls
    MAX_CATEGORIES_PER_TYPE: int = 25  # part-type category pages per appliance
    MAX_PARTS_PER_CATEGORY: int = 8    # parts pulled from each category page
    MAX_POPULAR_PARTS: int = 20        # popular parts from the main parts page
    MAX_MODELS_PER_TYPE: int = 30      # popular model URLs captured per appliance

    # Supported categories — adding a new one = uncomment a line
    SUPPORTED_CATEGORIES: List[str] = [
        "refrigerator",
        "dishwasher",
        # "washer",
        # "dryer",
    ]

    # PartSelect URLs
    PARTSELECT_BASE_URL: str = "https://www.partselect.com"
    # 365-day returns landing page: explains the policy AND has the "Start a
    # Return" CTA, so it doubles as both the "how do I return" and "what's your
    # return policy" destination. Returns are redirect-only (like order status).
    RETURNS_URL: str = "https://www.partselect.com/365-Day-Returns.htm"
    REPAIR_URLS: Dict[str, str] = {
        "refrigerator": "https://www.partselect.com/Repair/Refrigerator/",
        "dishwasher": "https://www.partselect.com/Repair/Dishwasher/",
    }
    PARTS_URLS: Dict[str, str] = {
        "refrigerator": "https://www.partselect.com/Refrigerator-Parts.htm",
        "dishwasher": "https://www.partselect.com/Dishwasher-Parts.htm",
    }

    # Pinecone namespaces
    NAMESPACE_PARTS: str = "parts"
    NAMESPACE_REPAIR: str = "repair-guides"
    NAMESPACE_MODEL_CACHE: str = "model-cache"

    # Where the model/brand catalog (mappings) is written by the scraper
    CATALOG_PATH: str = "data/catalog.json"

    # Pause between Firecrawl requests during bulk crawl (seconds)
    SCRAPE_DELAY_SECONDS: float = 1.0
    # Hard per-scrape wall-clock timeout (seconds). The Firecrawl SDK issues a
    # blocking HTTP call with no client timeout, so a slow/unknown page (e.g. an
    # unindexed part number that falls through to a live scrape) can hang the
    # whole /chat request indefinitely. We bound every scrape with this.
    FIRECRAWL_TIMEOUT_S: float = 20.0
    # Max scrape attempts for transient failures (5xx, network blips, 429s).
    # A genuine timeout is NOT retried — a hang is rarely transient and retrying
    # only multiplies the latency the user waits through.
    FIRECRAWL_MAX_ATTEMPTS: int = 3

    # ---------------------------------------------------------------------
    # Agentic discovery (scraper/agentic_discovery.py)
    # ---------------------------------------------------------------------
    # An LLM-planned, relevance-ranked alternative to the fixed-recipe crawl.
    # Strictly additive: the existing Tier-1 Pinecone + self-heal path is
    # unchanged. When ON, it runs as a live on-miss recovery layer in the
    # executor — but ONLY when a model number is known (the model page yields
    # exact compatible parts; without a model it can't be precise, so it's
    # skipped). A hard miss then tries to find + index the right content and
    # answer THIS turn instead of falling straight to a clarify prompt.
    ENABLE_AGENTIC_DISCOVERY: bool = True
    # Latency guardrails. Network scrapes — not the ~1s Flash plan/rank calls —
    # dominate runtime (each PartSelect page is ~10-20s via Firecrawl), so we cap
    # how many pages a single run may fetch and put a hard wall-clock ceiling on
    # the whole run. The budget is sized to fit ~2 scrapes (e.g. a repair guide
    # AND a parts page) so a run can return a real part card, while staying under
    # a minute end-to-end. On exceeding any cap the engine returns what it has
    # and the caller falls back gracefully.
    # Page cap is generous because doors are fetched CONCURRENTLY (one wave),
    # so more pages doesn't mean more wall-clock — the time budget + per-part
    # headroom guard are the real latency controls. Leaving room above the
    # typical 3 planned doors lets the reflect/re-plan loop try one more door.
    AGENTIC_MAX_PAGES: int = 5          # max page scrapes per discovery run
    AGENTIC_MAX_PARTS_INDEXED: int = 5  # max part pages indexed per run
    AGENTIC_TIME_BUDGET_S: float = 45.0  # overall wall-clock ceiling per run
    # Reflect → re-plan loop: after the first pass, if no relevant PARTS were
    # found and budget remains, the agent reasons about the gap and tries ONE
    # more targeted door. Capped so latency stays bounded — a re-plan scrape
    # only starts when the headroom guard confirms it can finish in budget, so
    # total runtime stays under the wall-clock ceiling.
    AGENTIC_REPLAN_MAX_LOOPS: int = 1

    # Embedding model.
    # NOTE: text-embedding-004 is not available on all Gemini accounts; the
    # newer gemini-embedding-001 is, and supports configurable output dims.
    # We request 768 dims to match the Pinecone index.
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 768

    # Load from .env; ignore any extra env vars (e.g. LANGCHAIN_TRACING_V2)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
