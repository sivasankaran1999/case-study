"""
One-time pre-indexing script.

Run from the backend/ directory:

    python -m scraper.scrape_runner

Discovers content dynamically from 4 seed URLs (2 parts pages + 2 repair
landings). Writes brand/model link maps to data/catalog.json and embeds
parts + repair guides into Pinecone.
"""

import json
import time
from pathlib import Path

from scraper.firecrawl_scraper import (
    scrape_page,
    extract_part_urls,
    extract_category_urls,
    extract_model_urls,
    extract_brand_map,
    extract_repair_symptom_urls,
    extract_model_number_from_url,
    part_type_from_category_url,
)
from scraper.indexer import index_repair_guide, index_part
from config.settings import settings


def _catalog_path() -> Path:
    path = Path(settings.CATALOG_PATH)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _save_catalog(catalog: dict):
    path = _catalog_path()
    path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(f"Catalog saved to {path}")


def _discover_main_page(category: str) -> dict:
    """Scrape the main parts page and extract all four sections."""
    base_url = settings.PARTS_URLS[category]
    print(f"\nScraping main page: {base_url}")
    scraped = scrape_page(base_url)
    markdown = scraped.get("content", "") or ""
    time.sleep(settings.SCRAPE_DELAY_SECONDS)

    categories = extract_category_urls(markdown, category)[
        : settings.MAX_CATEGORIES_PER_TYPE
    ]
    brands = extract_brand_map(markdown, category)
    models = extract_model_urls(markdown)[: settings.MAX_MODELS_PER_TYPE]
    popular_parts = extract_part_urls(markdown)[: settings.MAX_POPULAR_PARTS]

    model_map = {
        extract_model_number_from_url(url): url
        for url in models
        if extract_model_number_from_url(url)
    }

    print(
        f"  Discovered: {len(categories)} categories, {len(brands)} brands, "
        f"{len(model_map)} models, {len(popular_parts)} popular parts"
    )

    return {
        "categories": categories,
        "brands": brands,
        "models": model_map,
        "popular_parts": popular_parts,
    }


def _discover_repair_guides(category: str) -> list[str]:
    """Auto-discover symptom repair pages from the repair landing page."""
    landing = settings.REPAIR_URLS[category]
    print(f"\nDiscovering repair guides from: {landing}")
    scraped = scrape_page(landing)
    markdown = scraped.get("content", "") or ""
    time.sleep(settings.SCRAPE_DELAY_SECONDS)

    urls = extract_repair_symptom_urls(markdown, category)
    print(f"  Found {len(urls)} repair symptom pages")
    return urls


def run_full_index():
    """Main indexing pipeline: dynamic discovery + capped crawl."""
    print("=" * 60)
    print("PartSelect dynamic RAG indexing pipeline")
    print("=" * 60)

    catalog: dict = {}
    indexed_parts: set[str] = set()
    stats = {"parts": 0, "repairs": 0, "categories_crawled": 0}

    for category in settings.SUPPORTED_CATEGORIES:
        print(f"\n{'=' * 60}")
        print(f"APPLIANCE: {category.upper()}")
        print("=" * 60)

        discovery = _discover_main_page(category)
        catalog[category] = {
            "brands": discovery["brands"],
            "models": discovery["models"],
            "category_urls": discovery["categories"],
        }

        # Phase 1: repair guides (auto-discovered)
        print(f"\n--- Phase 1: Repair guides ({category}) ---")
        repair_urls = _discover_repair_guides(category)
        for url in repair_urls:
            try:
                index_repair_guide(url, category)
                stats["repairs"] += 1
            except Exception as e:
                print(f"Failed repair {url}: {e}")

        # Phase 2: popular parts from main page
        print(f"\n--- Phase 2: Popular parts ({category}) ---")
        for url in discovery["popular_parts"]:
            try:
                if index_part(url, category, skip_if_indexed=indexed_parts):
                    stats["parts"] += 1
            except Exception as e:
                print(f"Failed part {url}: {e}")

        # Phase 3: category crawl (one click deeper)
        print(f"\n--- Phase 3: Category crawl ({category}) ---")
        for cat_url in discovery["categories"]:
            part_type = part_type_from_category_url(cat_url, category)
            print(f"\n  Category: {cat_url} ({part_type})")
            try:
                scraped = scrape_page(cat_url)
                cat_markdown = scraped.get("content", "") or ""
                time.sleep(settings.SCRAPE_DELAY_SECONDS)

                part_urls = extract_part_urls(cat_markdown)[
                    : settings.MAX_PARTS_PER_CATEGORY
                ]
                stats["categories_crawled"] += 1
                print(f"    Found {len(part_urls)} parts (cap {settings.MAX_PARTS_PER_CATEGORY})")

                for part_url in part_urls:
                    try:
                        if index_part(
                            part_url,
                            category,
                            part_type=part_type,
                            skip_if_indexed=indexed_parts,
                        ):
                            stats["parts"] += 1
                    except Exception as e:
                        print(f"    Failed part {part_url}: {e}")
            except Exception as e:
                print(f"  Failed category {cat_url}: {e}")

    _save_catalog(catalog)

    print("\n" + "=" * 60)
    print("Indexing complete!")
    print(f"  Parts indexed:      {stats['parts']}")
    print(f"  Repair guides:      {stats['repairs']}")
    print(f"  Categories crawled: {stats['categories_crawled']}")
    print(f"  Unique part URLs:   {len(indexed_parts)}")
    print("=" * 60)


if __name__ == "__main__":
    run_full_index()
