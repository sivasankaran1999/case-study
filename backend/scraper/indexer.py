import hashlib
import json
import re
import time

from scraper.firecrawl_scraper import (
    scrape_page,
    scrape_part_page,
    extract_part_numbers,
    extract_model_number_from_url,
)
from rag.pinecone_client import upsert_documents, upsert_single
from rag.llm import extract_part_details, extract_symptom_tags
from config.settings import settings


def _part_number_from_url(url: str) -> str:
    match = re.search(r"(PS\d+)", url, re.IGNORECASE)
    return match.group(1).upper() if match else ""


def _part_name_from_url(url: str) -> str:
    """Derive a readable name from any PartSelect part URL slug.

    Handles both .../PS123-...-Part.htm and .../PS123-...-Bin.htm etc. by
    taking the slug after the manufacturer-number segment.
    """
    match = re.search(r"PS\d+-(.+?)\.htm", url, re.IGNORECASE)
    if not match:
        return ""
    slug = match.group(1)
    # Drop a trailing "-Part" qualifier if present.
    slug = re.sub(r"-Part$", "", slug, flags=re.IGNORECASE)
    words = slug.split("-")
    # The first 1-2 tokens are usually the brand + mfr part number; keep the
    # descriptive remainder when it looks like a name.
    if len(words) > 2 and re.search(r"\d", words[1]):
        words = words[2:]
    elif len(words) > 1 and re.fullmatch(r"[A-Z0-9]+", words[1] or ""):
        words = words[2:] if len(words) > 2 else words
    return " ".join(words).replace("  ", " ").strip()


def _price_from_markdown(markdown: str) -> str:
    match = re.search(r"\$\s*(\d+\.\d{2})", markdown)
    return match.group(1) if match else ""


def _image_from_markdown(markdown: str, part_number: str) -> str:
    """Extract the main product image URL from a part page's markdown.

    PartSelect product images live on the Azure CDN and embed the part's digits,
    e.g. .../11752778-1-M-Whirlpool-...-Bin.jpg ('-M-' is the medium/main image).
    """
    if not markdown:
        return ""
    digits = re.sub(r"\D", "", part_number or "")
    img_urls = re.findall(r"!\[[^\]]*\]\((https?://[^)]+\.(?:jpg|jpeg|png))\)", markdown, re.I)

    if digits:
        # Prefer the medium main image for this exact part.
        for size in ("-M-", "-S-", "-"):
            for u in img_urls:
                if f"/{digits}{size}" in u or f"/{digits}-1{size}" in u:
                    return u
        for u in img_urls:
            if digits in u:
                return u
    # Fallback: first CDN product image that isn't a logo/brand/nav asset.
    for u in img_urls:
        low = u.lower()
        if any(skip in low for skip in ("logo", "/brands/", "/images/", "flag", "vwo.io", "ytimg")):
            continue
        return u
    return ""


def _symptom_from_repair_url(url: str) -> str:
    """.../Repair/Dishwasher/Leaking/ -> leaking"""
    match = re.search(r"/Repair/[^/]+/([^/]+)/?", url)
    if not match:
        return ""
    return match.group(1).replace("-", " ").lower()


# YouTube IDs are exactly 11 chars of [A-Za-z0-9_-]. PartSelect embeds its
# installation videos as YouTube players, which surface in scraped markdown as
# an embed/watch link or a thumbnail (i.ytimg.com/vi/<id>/...). Channel links
# (youtube.com/@PartSelect, /user/PartSelect) have no 11-char id after these
# markers, so they won't match.
_YT_ID = r"([A-Za-z0-9_-]{11})"
_VIDEO_PATTERNS = (
    re.compile(rf"youtube(?:-nocookie)?\.com/embed/{_YT_ID}", re.I),
    re.compile(rf"(?:i\.)?ytimg\.com/vi/{_YT_ID}/", re.I),
    re.compile(rf"img\.youtube\.com/vi/{_YT_ID}/", re.I),
    re.compile(rf"youtube\.com/watch\?v={_YT_ID}", re.I),
    re.compile(rf"youtu\.be/{_YT_ID}", re.I),
)


def extract_video_url(markdown: str) -> str:
    """Return a canonical YouTube embed URL for the part's installation video,
    or "" if none is present. Patterns are tried in priority order (actual
    embedded player first, thumbnail next, plain watch/short links last)."""
    if not markdown:
        return ""
    for pat in _VIDEO_PATTERNS:
        m = pat.search(markdown)
        if m:
            return f"https://www.youtube.com/embed/{m.group(1)}"
    return ""


def _delete_part_chunks(url_hash: str, keep: int = 0, span: int = 60):
    """Delete prior part chunk ids for this URL hash beyond the kept range."""
    stale_ids = [f"part_{url_hash}_{i}" for i in range(keep, span)]
    if not stale_ids:
        return
    try:
        from rag.pinecone_client import index as _idx
        _idx.delete(ids=stale_ids, namespace=settings.NAMESPACE_PARTS)
    except Exception as e:
        print(f"Stale-chunk cleanup skipped: {e}")


def focus_part_content(markdown: str) -> str:
    """Trim leading site navigation so the LLM sees the actual part content.

    PartSelect part pages carry ~25k chars of global nav before the product
    block. Anchor on the first real part marker and keep from there.
    """
    if not markdown:
        return markdown
    anchors = [
        "PartSelect Number",
        "Manufacturer Part Number",
        "Product Description",
        "Installation Instructions",
    ]
    positions = [markdown.find(a) for a in anchors]
    positions = [p for p in positions if p != -1]
    if not positions:
        return markdown
    start = max(0, min(positions) - 400)
    return markdown[start:]


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks


def index_repair_guide(url: str, category: str):
    """Scrape and index a repair guide page into Pinecone (repair-guides namespace)."""
    print(f"Indexing repair guide: {url}")
    scraped = scrape_page(url)
    markdown = scraped.get("content", "") or ""

    if not markdown:
        print(f"No content found for {url}")
        return

    symptom = _symptom_from_repair_url(url)
    symptom_tags = extract_symptom_tags(markdown, category)
    if symptom and symptom not in symptom_tags:
        symptom_tags.insert(0, symptom)

    recommended = extract_part_numbers(markdown)[:20]

    base_meta = {
        "url": url,
        "category": category,
        "type": "repair_guide",
        "symptom": symptom,
        "symptom_tags": json.dumps(symptom_tags),
        "recommended_parts": json.dumps(recommended),
    }

    prefix = (
        f"Repair guide: {symptom}. Appliance: {category}. "
        f"Symptoms: {', '.join(symptom_tags)}. "
    )
    chunks = chunk_text(markdown)
    url_hash = hashlib.md5(url.encode()).hexdigest()
    documents = []

    for i, chunk in enumerate(chunks):
        documents.append(
            {
                "id": f"repair_{url_hash}_{i}",
                "text": prefix + chunk,
                "metadata": {**base_meta, "chunk_index": i},
            }
        )

    upsert_documents(documents, namespace=settings.NAMESPACE_REPAIR)
    print(f"Indexed {len(documents)} chunks from {url}")
    time.sleep(settings.SCRAPE_DELAY_SECONDS)


def index_part(
    part_url: str,
    category: str,
    part_type: str = "",
    brand: str = "",
    skip_if_indexed: set | None = None,
) -> bool:
    """
    Scrape and index a part page into Pinecone (parts namespace).
    Returns True if indexed, False if skipped (duplicate).
    """
    part_number = _part_number_from_url(part_url)
    if skip_if_indexed is not None:
        if part_number and part_number in skip_if_indexed:
            return False
        if part_url in skip_if_indexed:
            return False

    print(f"Indexing part: {part_url}")
    scraped = scrape_part_page(part_url)
    markdown = scraped.get("content", "") or ""

    if not markdown:
        print(f"No content found for {part_url}")
        return False

    extracted_fc = scraped.get("extracted", {}) or {}
    focused = focus_part_content(markdown)
    llm = extract_part_details(focused, category)

    part_number = (
        extracted_fc.get("part_number")
        or _part_number_from_url(part_url)
        or part_number
    )
    part_name = (
        llm.get("part_name")
        or extracted_fc.get("part_name")
        or _part_name_from_url(part_url)
    )
    price = str(
        llm.get("price")
        or extracted_fc.get("price")
        or _price_from_markdown(markdown)
        or ""
    )
    fixes_symptoms = llm.get("fixes_symptoms") or []
    compatible = llm.get("compatible_models") or extracted_fc.get("compatible_models") or []
    install_steps = llm.get("installation_steps") or extracted_fc.get("installation_steps") or []
    description = llm.get("description") or extracted_fc.get("description") or ""

    in_stock_val = llm.get("in_stock")
    if in_stock_val is None:
        in_stock_val = extracted_fc.get("in_stock")
    if in_stock_val is None:
        in_stock_val = "in stock" in markdown.lower()

    base_meta = {
        "url": part_url,
        "category": category,
        "type": "part",
        "part_number": part_number,
        "part_name": part_name,
        "description": description[:500],
        "price": price,
        "in_stock": bool(in_stock_val),
        "fixes_symptoms": json.dumps(fixes_symptoms),
        "compatible_models": json.dumps(compatible),
        "installation_steps": json.dumps(install_steps[:12]),
        "part_type": part_type,
        "brand": brand,
        "image_url": (
            extracted_fc.get("image_url", "")
            or _image_from_markdown(markdown, part_number)
            or ""
        ),
        "video_url": extract_video_url(markdown),
        "product_url": part_url,
    }

    prefix = (
        f"Part: {part_name}. Part Number: {part_number}. "
        f"Category: {category}. Type: {part_type}. Brand: {brand}. "
        f"Fixes: {', '.join(fixes_symptoms)}. "
        f"Compatible models: {', '.join(compatible[:10])}. "
    )
    chunks = chunk_text(focused, chunk_size=400, overlap=40)
    url_hash = hashlib.md5(part_url.encode()).hexdigest()
    documents = []

    for i, chunk in enumerate(chunks):
        documents.append(
            {
                "id": f"part_{url_hash}_{i}",
                "text": prefix + chunk,
                "metadata": {**base_meta, "chunk_index": i},
            }
        )

    # Remove any stale chunks from a prior indexing of this URL so re-indexing
    # with fewer chunks doesn't leave orphaned (sparse) vectors behind.
    _delete_part_chunks(url_hash, keep=len(documents))

    upsert_documents(documents, namespace=settings.NAMESPACE_PARTS)
    print(f"Indexed part: {part_number or 'unknown'} ({len(documents)} chunks)")

    if skip_if_indexed is not None:
        if part_number:
            skip_if_indexed.add(part_number)
        skip_if_indexed.add(part_url)

    time.sleep(settings.SCRAPE_DELAY_SECONDS)
    return True


def index_model_cache(model_url: str, category: str, markdown: str | None = None):
    """
    Index a model page into the model-cache namespace.
    Stores model -> compatible part numbers for fast compatibility lookups.
    """
    model_number = extract_model_number_from_url(model_url)
    if not model_number:
        print(f"Could not parse model number from {model_url}")
        return

    if markdown is None:
        scraped = scrape_page(model_url)
        markdown = scraped.get("content", "") or ""

    if not markdown:
        print(f"No content for model {model_number}")
        return

    compatible_parts = extract_part_numbers(markdown)
    text = (
        f"Model {model_number} ({category}) compatible parts: "
        f"{', '.join(compatible_parts)}"
    )
    metadata = {
        "type": "model_cache",
        "model_number": model_number,
        "category": category,
        "url": model_url,
        "compatible_parts": json.dumps(compatible_parts),
        "part_count": len(compatible_parts),
    }

    doc_id = f"model_{model_number}"
    upsert_single(doc_id, text, metadata, namespace=settings.NAMESPACE_MODEL_CACHE)
    print(f"Cached model {model_number} with {len(compatible_parts)} parts")
    time.sleep(settings.SCRAPE_DELAY_SECONDS)
