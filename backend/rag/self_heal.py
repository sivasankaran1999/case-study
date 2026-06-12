"""
Self-healing RAG: three-tier lookup for parts and models.

Tier 1: Pinecone (pre-indexed)
Tier 2: Live Firecrawl scrape (construct URL -> scrape -> upsert)
Tier 3: PartSelect search fallback (search -> scrape first hit -> upsert)
"""

import json
import re
import time
from pathlib import Path

from scraper.firecrawl_scraper import (
    scrape_page,
    construct_model_url,
    construct_part_url,
    construct_search_url,
    extract_part_urls,
    extract_part_numbers,
    extract_model_number_from_url,
)
from scraper.indexer import index_part, index_model_cache
from rag.pinecone_client import query_index, index as pinecone_index
from config.settings import settings


def parse_json_field(value, default=None):
    default = [] if default is None else default
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else default
        except (json.JSONDecodeError, TypeError):
            return default
    return default


def _load_catalog() -> dict:
    path = Path(settings.CATALOG_PATH)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_part_number(part_number: str) -> str:
    pn = part_number.upper().strip()
    if not pn.startswith("PS"):
        pn = f"PS{pn}"
    return pn


def _normalize_model_number(model_number: str) -> str:
    return model_number.upper().strip()


def _is_metadata_complete(meta: dict) -> bool:
    """A part record is 'complete' when it has the fields needed for a good
    answer. Sparse early-crawl records (empty name / no symptoms / no install)
    are treated as incomplete so we re-scrape and self-heal."""
    if not meta:
        return False
    if not (meta.get("part_name") or "").strip():
        return False
    if not (meta.get("image_url") or "").strip():
        return False
    has_symptoms = parse_json_field(meta.get("fixes_symptoms"))
    has_install = parse_json_field(meta.get("installation_steps"))
    has_desc = bool((meta.get("description") or "").strip())
    # Need a product image, a description, and one of symptoms/installation.
    return has_desc and (bool(has_symptoms) or bool(has_install))


def _query_hits_for_part(pn: str, top_k: int = 10) -> list[dict]:
    """Merge Pinecone hits from multiple query phrasings for exact PS lookup.

    Some parts rank under the bare PS number, others under 'part number PS…' —
    try both and dedupe so clarify-option clicks always resolve.
    """
    seen: set[str] = set()
    merged: list[dict] = []
    for query in (pn, f"part number {pn}"):
        for hit in query_index(query, namespace=settings.NAMESPACE_PARTS, top_k=top_k):
            hid = hit.get("id")
            if hid and hid in seen:
                continue
            if hid:
                seen.add(hid)
            merged.append(hit)
    return merged


def _reindex_and_fetch(part_url: str, pn: str, category: str) -> dict | None:
    """Live re-scrape a known part URL, re-upsert, and return fresh metadata."""
    index_part(part_url, category or "dishwasher")
    exact = _find_exact_hit(_query_hits_for_part(pn, top_k=10), pn)
    if exact:
        return {
            "source": "live_refresh",
            "confidence": exact["confidence"],
            **exact.get("metadata", {}),
        }
    return None


_GENERIC_PART_URL_RE = re.compile(r"/PS\d+-Part\.htm$", re.I)


def _is_generic_part_url(url: str) -> bool:
    """True for bare /PS12345-Part.htm URLs that often scrape cross-sell junk."""
    return bool(url and _GENERIC_PART_URL_RE.search(url))


def _fetch_exact_after_index(
    pn: str, source: str, attempts: int = 3, delay_s: float = 0.5
) -> dict | None:
    """Re-query Pinecone after an upsert; brief retries handle index lag."""
    for i in range(attempts):
        exact = _find_exact_hit(_query_hits_for_part(pn), pn)
        if exact:
            return {
                "source": source,
                "confidence": exact["confidence"],
                **exact.get("metadata", {}),
            }
        if i < attempts - 1:
            time.sleep(delay_s)
    return None


def _lookup_via_direct_url(pn: str, category: str) -> dict | None:
    """Scrape the canonical /PS…-Part.htm page directly, index it, and return.

    For an EXACT part number the URL is deterministic, so we hit the part page
    straight away instead of the (slow, sometimes-hanging) site-search page. The
    generic page can carry cross-sell links, but extraction anchors on the
    product block and `_find_exact_hit` requires an exact part-number match
    downstream, so a wrong part can't leak through. This is the Tier-2 the module
    docstring always promised — it was missing from `lookup_part`.
    """
    url = construct_part_url(pn)
    index_part(url, category or "dishwasher")
    return _fetch_exact_after_index(pn, "direct_url")


def _lookup_via_search(pn: str, category: str) -> dict | None:
    """Find the canonical product URL via PartSelect search, index, and return."""
    search_url = construct_search_url(pn)
    scraped = scrape_page(search_url)
    markdown = scraped.get("content", "") or ""
    for url in extract_part_urls(markdown):
        if pn not in url.upper() or _is_generic_part_url(url):
            continue
        index_part(url, category or "dishwasher")
        result = _fetch_exact_after_index(pn, "search_fallback")
        if result:
            return result
    return None


def _find_exact_hit(hits: list[dict], pn: str) -> dict | None:
    """Return the best hit whose part_number matches pn exactly, if any.

    When duplicate vectors exist for the same part number (e.g. a rich record
    plus a sparse/mislabeled one from a generic '-Part.htm' scrape), prefer the
    COMPLETE record. Otherwise a sparse duplicate can win on ranking noise and
    surface a wrong, detail-less card for an exact lookup.
    """
    exact = [
        hit for hit in hits
        if hit.get("metadata", {}).get("part_number", "").upper() == pn
    ]
    if not exact:
        return None
    for hit in exact:
        if _is_metadata_complete(hit.get("metadata", {})):
            return hit
    # No complete record — return the first so Tier-1 self-heal can refresh it.
    return exact[0]


def lookup_part(part_number: str, category: str = "") -> dict | None:
    """
    Three-tier part lookup for an EXPLICIT part number. Always returns the exact
    part requested or None — never a different (semantically similar) part.
    Price/stock in metadata are hints only — always re-verify live at answer time.
    """
    pn = _normalize_part_number(part_number)

    # Tier 1: Pinecone — scan a wide window and require an EXACT part-number
    # match. Semantically similar parts (e.g. PS11739122 for PS11739119) must
    # never be returned for a specific lookup.
    exact = _find_exact_hit(_query_hits_for_part(pn), pn)
    if exact:
        meta = exact.get("metadata", {})
        if not _is_metadata_complete(meta):
            stored_url = meta.get("url") or meta.get("product_url")
            # Generic /PS…-Part.htm pages often scrape cross-sell junk — skip them.
            if stored_url and not _is_generic_part_url(stored_url):
                try:
                    refreshed = _reindex_and_fetch(stored_url, pn, category)
                    if refreshed:
                        return refreshed
                except Exception as e:
                    print(f"Self-heal refresh failed for {pn}: {e}")
            # Fall through to search-based scrape.
        else:
            return {"source": "pinecone", "confidence": exact["confidence"], **meta}

    # Tier 2: scrape the canonical /PS…-Part.htm page directly. Deterministic URL,
    # so it's faster and far more reliable than site search for an exact lookup.
    try:
        found = _lookup_via_direct_url(pn, category)
        if found:
            return found
    except Exception as e:
        print(f"Tier 2 direct-URL lookup failed for {pn}: {e}")

    # Tier 3: PartSelect search → canonical product URL (last resort if the
    # direct page didn't yield a complete, indexable record).
    try:
        found = _lookup_via_search(pn, category)
        if found:
            return found
    except Exception as e:
        print(f"Tier 3 search lookup failed for {pn}: {e}")

    return None


def _get_model_from_cache(model_number: str) -> dict | None:
    """Fetch model-cache record directly by ID."""
    model_number = _normalize_model_number(model_number)
    try:
        result = pinecone_index.fetch(
            ids=[f"model_{model_number}"],
            namespace=settings.NAMESPACE_MODEL_CACHE,
        )
        vectors = result.get("vectors") or {}
        vec = vectors.get(f"model_{model_number}")
        if vec:
            return vec.get("metadata", {})
    except Exception:
        pass
    return None


def get_model_compatible_parts(model_number: str, category: str = "") -> set | None:
    """Return the set of PS numbers compatible with a model.

    Cache-first; on a miss, does ONE live scrape of the model page and caches it.
    Returns None when we can't determine the list (so callers can avoid making
    false 'does not fit' claims).
    """
    model = _normalize_model_number(model_number)
    cached = _get_model_from_cache(model)
    if cached:
        try:
            return {p.upper() for p in json.loads(cached.get("compatible_parts", "[]"))}
        except (json.JSONDecodeError, TypeError):
            return None

    try:
        model_url = construct_model_url(model)
        scraped = scrape_page(model_url)
        markdown = scraped.get("content", "") or ""
        if not markdown:
            return None
        parts = extract_part_numbers(markdown)
        index_model_cache(model_url, category or "dishwasher", markdown=markdown)
        return {p.upper() for p in parts}
    except Exception as e:
        print(f"Model compat lookup failed for {model}: {e}")
        return None


def check_compatibility(part_number: str, model_number: str, category: str = "") -> dict:
    """
    Check if a part is compatible with a model.
    Uses model-cache first, then live-scrapes the model page and upserts cache.
    """
    pn = _normalize_part_number(part_number)
    model = _normalize_model_number(model_number)

    cached = _get_model_from_cache(model)
    if cached:
        parts = json.loads(cached.get("compatible_parts", "[]"))
        compatible = pn in parts
        return {
            "compatible": compatible,
            "source": "model_cache",
            "model_number": model,
            "part_number": pn,
            "model_url": cached.get("url", construct_model_url(model)),
        }

    # Live scrape model page
    model_url = construct_model_url(model)
    try:
        scraped = scrape_page(model_url)
        markdown = scraped.get("content", "") or ""
        if not markdown:
            return {
                "compatible": False,
                "source": "not_found",
                "model_number": model,
                "part_number": pn,
                "model_url": model_url,
            }

        parts = extract_part_numbers(markdown)
        index_model_cache(model_url, category or "dishwasher", markdown=markdown)

        return {
            "compatible": pn in parts,
            "source": "live_scrape",
            "model_number": model,
            "part_number": pn,
            "model_url": model_url,
            "compatible_parts_count": len(parts),
        }
    except Exception as e:
        return {
            "compatible": False,
            "source": "error",
            "error": str(e),
            "model_number": model,
            "part_number": pn,
            "model_url": model_url,
        }


def lookup_repair_guide(symptom_query: str, top_k: int = 5) -> list[dict]:
    """
    Repair-guide lookup with self-heal. If the best Pinecone match is weak,
    re-scrape that guide's source URL and re-upsert, then re-query.
    """
    from scraper.indexer import index_repair_guide

    hits = query_index(symptom_query, namespace=settings.NAMESPACE_REPAIR, top_k=top_k)
    if not hits:
        return hits

    top = hits[0]
    # Trust a reasonably-strong match as-is. Only genuinely weak matches fall
    # through to a live re-scrape — otherwise every query re-scrapes (good
    # symptom matches score ~0.73-0.76, below the old 0.8 threshold) and pays
    # ~12s for identical content.
    if top.get("confidence", 0.0) >= settings.REPAIR_SELF_HEAL_FLOOR:
        return hits

    # Weak match -> refresh the source guide and re-query.
    meta = top.get("metadata", {})
    url = meta.get("url")
    category = meta.get("category", "")
    if url:
        try:
            index_repair_guide(url, category or "dishwasher")
            refreshed = query_index(
                symptom_query, namespace=settings.NAMESPACE_REPAIR, top_k=top_k
            )
            if refreshed:
                return refreshed
        except Exception as e:
            print(f"Repair self-heal failed for {url}: {e}")
    return hits


def lookup_brand_page(brand: str, category: str) -> str | None:
    """Resolve a brand page URL from catalog.json."""
    catalog = _load_catalog()
    cat_data = catalog.get(category, {})
    brands = cat_data.get("brands", {})
    return brands.get(brand) or brands.get(brand.title())


def scrape_brand_popular_parts(brand: str, category: str, limit: int = 10) -> list[str]:
    """
    Live-scrape a brand page and upsert popular parts found there.
    Returns list of part numbers indexed.
    """
    brand_url = lookup_brand_page(brand, category)
    if not brand_url:
        return []

    scraped = scrape_page(brand_url)
    markdown = scraped.get("content", "") or ""
    part_urls = extract_part_urls(markdown)[:limit]
    indexed = []

    for url in part_urls:
        try:
            if index_part(url, category, brand=brand):
                pn = re.search(r"(PS\d+)", url, re.IGNORECASE)
                if pn:
                    indexed.append(pn.group(1).upper())
        except Exception as e:
            print(f"Failed to index brand part {url}: {e}")

    return indexed


def _classify_availability(window_lower: str) -> tuple[bool, str]:
    """Map a part page's availability text to (orderable, label).

    PartSelect availability is NOT binary. Besides "In Stock", a part can be on
    "Special Order" — still fully orderable, just with a longer lead time — or
    "No Longer Available" / discontinued (genuinely not orderable). Treating
    anything that isn't the literal "in stock" as out-of-stock wrongly flags
    Special-Order parts as unavailable. Checked most-specific first.
    """
    if "no longer available" in window_lower or "discontinued" in window_lower:
        return False, "Discontinued"
    if "out of stock" in window_lower:
        return False, "Out of Stock"
    if "special order" in window_lower:
        return True, "Special Order"
    if "in stock" in window_lower:
        return True, "In Stock"
    # A live "Add to cart" control with no negative signal still means orderable.
    if "add to cart" in window_lower:
        return True, "Available"
    return False, ""


def get_live_price_stock(part_url: str) -> dict:
    """
    Always fetch current price and stock from a live scrape.
    Never trust cached Pinecone values for these fields.

    Also extracts the part's installation video (when present) from the same
    scrape so exact lookups surface it without a separate request or a full
    re-index of the parts namespace.
    """
    from scraper.indexer import extract_video_url

    scraped = scrape_page(part_url)
    markdown = scraped.get("content", "") or ""
    lower = markdown.lower()

    # Anchor on the main product's "Add to cart" block; the part's own price and
    # stock status sit just above it (related parts appear far below).
    anchor = lower.find("add to cart")
    if anchor != -1:
        window = markdown[max(0, anchor - 400):anchor + 50]
    else:
        window = markdown[:2000]
    wlower = window.lower()

    price_match = re.search(r"\$\s*(\d+\.\d{2})", window) or re.search(
        r"\$\s*(\d+\.\d{2})", markdown
    )
    in_stock, availability = _classify_availability(wlower)

    return {
        "price": price_match.group(1) if price_match else None,
        "in_stock": in_stock,
        "availability": availability,
        "video_url": extract_video_url(markdown),
        "url": part_url,
    }
