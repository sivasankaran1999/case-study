"""Pluggable scraper backend.

WHY THIS EXISTS
---------------
Today every scrape goes straight through Firecrawl (``scraper.firecrawl_scraper``).
That works, but it hard-couples the whole pipeline to one vendor: swapping to
Playwright, an internal crawler, or a cached fixture store for tests would mean
editing every call site.

This module introduces a tiny ``ScraperBackend`` interface (a ``typing.Protocol``)
so the rest of the system depends on an *abstraction*, not on Firecrawl. The
default ``FirecrawlBackend`` simply delegates to the existing, battle-tested
functions — so behavior is unchanged — but a different backend can be dropped in
without touching the agentic discovery engine, the indexer, or self-heal.

This is the "best practices + scalability" seam: the code is ready to scale to a
different/parallel infrastructure even if we keep Firecrawl for now.
"""

from __future__ import annotations

import concurrent.futures
from typing import Protocol, runtime_checkable

from scraper.firecrawl_scraper import scrape_page, scrape_part_page

# Dedicated pool for the OUTER parallel-fetch fan-out. It must be separate from
# firecrawl_scraper._scrape_pool: each scrape_page() call already submits its
# blocking HTTP request to that inner pool to enforce a timeout, so fanning out
# on the same pool would nest submissions and starve/deadlock it. Using a
# distinct pool keeps the two layers independent.
_fetch_pages_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="fetch-pages"
)


@runtime_checkable
class ScraperBackend(Protocol):
    """Minimal contract any scraper must satisfy.

    Both methods return the same dict shape the rest of the codebase already
    expects from ``firecrawl_scraper`` (``{"url", "content", "metadata", ...}``),
    so backends are interchangeable with zero downstream changes.
    """

    def fetch_page(self, url: str) -> dict:
        """Scrape a generic page → markdown + metadata."""
        ...

    def fetch_part_page(self, url: str) -> dict:
        """Scrape a part page → markdown + best-effort structured extract."""
        ...

    def fetch_pages(self, urls: list[str]) -> dict[str, dict]:
        """Scrape several pages concurrently → {url: result}."""
        ...


class FirecrawlBackend:
    """Default backend: delegates to the existing Firecrawl wrappers.

    Deliberately thin — it adds the swappable seam without changing any
    scraping behavior (same timeouts, retries, and return shapes as before).
    """

    name = "firecrawl"

    def fetch_page(self, url: str) -> dict:
        return scrape_page(url)

    def fetch_part_page(self, url: str) -> dict:
        return scrape_part_page(url)

    def fetch_pages(self, urls: list[str]) -> dict[str, dict]:
        """Scrape multiple pages CONCURRENTLY on the shared scrape pool.

        Independent doors (e.g. a model page AND a repair landing) have no data
        dependency, so fetching them in parallel turns N sequential ~15-20s
        scrapes into a single ~15-20s wave — the core "handles scale" win and
        what keeps the re-plan loop affordable under the latency budget. Each
        scrape keeps its own per-request timeout/retry; a failure on one URL
        maps to an empty result for that URL and never aborts the others.
        """
        if not urls:
            return {}
        futures = {url: _fetch_pages_pool.submit(scrape_page, url) for url in urls}
        results: dict[str, dict] = {}
        for url, fut in futures.items():
            try:
                results[url] = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"Parallel fetch failed for {url}: {e}")
                results[url] = {"url": url, "content": "", "metadata": {}}
        return results


# Module-level default. Callers import this rather than Firecrawl directly, so a
# future swap is a one-line change here (or an injected argument).
default_backend: ScraperBackend = FirecrawlBackend()
