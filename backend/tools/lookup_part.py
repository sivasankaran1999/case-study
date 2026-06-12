"""Tool: look up a specific part by part number (RAG first, live scrape fallback)."""

from rag.self_heal import lookup_part, get_live_price_stock


def run(part_number: str, category: str = "") -> dict | None:
    result = lookup_part(part_number, category=category)
    if not result:
        return None

    url = result.get("url") or result.get("product_url")
    if url:
        try:
            live = get_live_price_stock(url)
            result["price"] = live.get("price") or result.get("price")
            result["in_stock"] = live.get("in_stock")
            result["availability"] = live.get("availability") or ""
            # Prefer a freshly-scraped video; fall back to any indexed one.
            result["video_url"] = live.get("video_url") or result.get("video_url", "")
        except Exception:
            pass  # use cached metadata when live scrape unavailable

    return result
