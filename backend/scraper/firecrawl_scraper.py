import concurrent.futures
import hashlib
import re

from firecrawl import FirecrawlApp
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
    retry_if_not_exception_type,
)

from config.settings import settings

app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)

# Dedicated pool so a hung scrape can be abandoned via Future.result(timeout=...).
# The Firecrawl SDK's HTTP call is blocking with no client-side timeout, so this
# is the only reliable way to stop a single request from hanging the whole app.
_scrape_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="firecrawl"
)


class RateLimitError(Exception):
    """Raised when Firecrawl returns a 429 so Tenacity can back off and retry."""


class ScrapeTimeout(Exception):
    """A single scrape exceeded FIRECRAWL_TIMEOUT_S. Deliberately NOT retried —
    a hang is rarely transient, and retrying only multiplies the wait the user
    sits through. The caller's try/except degrades to cached data or None."""


def _looks_like_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


def _scrape_url(url: str, params: dict) -> dict:
    """Run one Firecrawl scrape, bounded by a hard wall-clock timeout.

    Normalizes 429s to RateLimitError (so backoff is intentional) and a hang to
    ScrapeTimeout (which is not retried)."""
    future = _scrape_pool.submit(app.scrape_url, url, params=params)
    try:
        return future.result(timeout=settings.FIRECRAWL_TIMEOUT_S)
    except concurrent.futures.TimeoutError as e:
        future.cancel()  # best-effort; the worker thread is abandoned
        raise ScrapeTimeout(f"scrape exceeded {settings.FIRECRAWL_TIMEOUT_S}s: {url}") from e
    except Exception as e:
        if _looks_like_rate_limit(e):
            raise RateLimitError(str(e)) from e
        raise


# Retry transient failures (network blips, 5xx, 429s) with exponential backoff,
# but NEVER retry a hard timeout — see ScrapeTimeout. After the final attempt the
# caller's try/except keeps the pipeline from crashing.
_retry = retry(
    wait=wait_exponential(multiplier=2, min=2, max=15),
    stop=stop_after_attempt(settings.FIRECRAWL_MAX_ATTEMPTS),
    retry=(
        retry_if_exception_type(Exception)
        & retry_if_not_exception_type(ScrapeTimeout)
    ),
    reraise=True,
)


@_retry
def scrape_page(url: str) -> dict:
    """
    Scrape a single page using Firecrawl, returning clean markdown + metadata.
    Bounded by a hard timeout; retries transient failures (incl. 429s).
    """
    result = _scrape_url(url, {"formats": ["markdown"]})
    content = result.get("markdown") or result.get("content") or ""
    return {
        "url": url,
        "content": content,
        "metadata": result.get("metadata", {}),
        "id": hashlib.md5(url.encode()).hexdigest(),
    }


@_retry
def scrape_part_page(part_url: str) -> dict:
    """
    Scrape a specific PartSelect part page (markdown + best-effort extract).
    """
    result = _scrape_url(
        part_url,
        {
            "formats": ["markdown", "extract"],
            "extract": {
                "schema": {
                    "part_number": "string",
                    "part_name": "string",
                    "description": "string",
                    "price": "string",
                    "in_stock": "boolean",
                    "compatible_models": "array",
                    "installation_steps": "array",
                    "image_url": "string",
                }
            },
        },
    )
    content = result.get("markdown") or result.get("content") or ""
    return {
        "url": part_url,
        "content": content,
        "extracted": result.get("extract", {}) or result.get("llm_extraction", {}),
        "metadata": result.get("metadata", {}),
        "id": hashlib.md5(part_url.encode()).hexdigest(),
    }


# --------------------------------------------------------------------------
# Link discovery helpers — parse a category parts page's markdown to find the
# sublinks we crawl (part-type categories, individual parts, models, brands).
# --------------------------------------------------------------------------

def _appliance_word(category: str) -> str:
    return "Refrigerator" if category == "refrigerator" else "Dishwasher"


def extract_part_urls(markdown: str) -> list[str]:
    """Individual part page URLs (e.g. .../PS11752778-...-Part.htm or ...htm)."""
    urls = re.findall(r"https://www\.partselect\.com/PS\d+-[^\"\s)]+\.htm", markdown)
    return list(dict.fromkeys(urls))


def extract_category_urls(markdown: str, category: str) -> list[str]:
    """Part-type category pages, e.g. .../Dishwasher-Spray-Arms.htm.

    Excludes the top-level .../Dishwasher-Parts.htm itself.
    """
    word = _appliance_word(category)
    pattern = rf"https://www\.partselect\.com/{word}-[A-Za-z-]+\.htm"
    urls = re.findall(pattern, markdown)
    # Exclude the top-level parts page and the models-listing page — neither is
    # a part-type category.
    excluded = {f"/{word}-Parts.htm", f"/{word}-Models.htm"}
    cleaned = [
        u for u in dict.fromkeys(urls) if not any(u.endswith(x) for x in excluded)
    ]
    return cleaned


def extract_model_urls(markdown: str) -> list[str]:
    """Popular model pages, e.g. .../Models/WDT730PAHZ0/."""
    urls = re.findall(r"https://www\.partselect\.com/Models/[A-Za-z0-9]+/?", markdown)
    return list(dict.fromkeys(urls))


def extract_brand_map(markdown: str, category: str) -> dict:
    """Brand -> brand parts URL, e.g. {'Whirlpool': '.../Whirlpool-Dishwasher-Parts.htm'}."""
    word = _appliance_word(category)
    pattern = rf"https://www\.partselect\.com/([A-Za-z]+)-{word}-Parts\.htm"
    out = {}
    for m in re.finditer(pattern, markdown):
        brand = m.group(1)
        out.setdefault(brand, m.group(0))
    return out


def extract_repair_symptom_urls(markdown: str, category: str) -> list[str]:
    """Symptom repair pages from a repair landing page, e.g. .../Repair/Dishwasher/Leaking/."""
    word = _appliance_word(category)
    pattern = rf"https://www\.partselect\.com/Repair/{word}/[A-Za-z0-9-]+/?"
    landing = f"/Repair/{word}/"
    urls = []
    for url in re.findall(pattern, markdown):
        normalized = url.rstrip("/")
        if normalized.endswith(landing.rstrip("/")):
            continue
        urls.append(url if url.endswith("/") else url + "/")
    return list(dict.fromkeys(urls))


def extract_part_numbers(markdown: str) -> list[str]:
    """All PS part numbers mentioned on a page (model pages, brand pages, etc.)."""
    nums = re.findall(r"\b(PS\d+)\b", markdown, re.IGNORECASE)
    return list(dict.fromkeys(n.upper() for n in nums))


def extract_model_number_from_url(url: str) -> str:
    match = re.search(r"/Models/([A-Za-z0-9]+)", url, re.IGNORECASE)
    return match.group(1).upper() if match else ""


def part_type_from_category_url(url: str, category: str) -> str:
    """e.g. .../Dishwasher-Spray-Arms.htm -> spray_arms"""
    word = _appliance_word(category)
    match = re.search(rf"/{word}-([A-Za-z-]+)\.htm", url, re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).lower().replace("-", "_")


def construct_part_url(part_number: str) -> str:
    """Construct a PartSelect URL for a specific part number (agentic lookup)."""
    pn = part_number.upper().strip()
    if not pn.startswith("PS"):
        pn = f"PS{pn}"
    return f"{settings.PARTSELECT_BASE_URL}/{pn}-Part.htm"


def construct_model_url(model_number: str) -> str:
    """Construct a PartSelect model page URL, e.g. /Models/FPHD2491KF0/."""
    return f"{settings.PARTSELECT_BASE_URL}/Models/{model_number.upper().strip()}/"


def construct_search_url(query: str) -> str:
    """PartSelect site search fallback (Tier 3)."""
    from urllib.parse import quote_plus

    return f"{settings.PARTSELECT_BASE_URL}/Search.aspx?SearchTerm={quote_plus(query)}"
