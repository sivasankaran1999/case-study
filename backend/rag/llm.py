"""Gemini Flash structured-extraction helpers used at index time.

Firecrawl's legacy `extract` schema returns empty on the 0.0.16 client, so we
use Gemini Flash to pull structured fields out of scraped markdown:
- repair pages -> symptom tags
- part pages   -> description, fixes_symptoms, compatible_models, install steps
"""

import json
import re

import google.generativeai as genai
from tenacity import retry, wait_exponential, stop_after_attempt

from config.settings import settings
from observability import record_llm_call, timer, usage_from_response

genai.configure(api_key=settings.GEMINI_API_KEY.strip())

# Fast model: structured extraction, tagging (high volume, cheap).
_model = genai.GenerativeModel(settings.LLM_FAST_MODEL)
# Strong model: final answer synthesis / reasoning (low volume, quality).
_reasoning_model = genai.GenerativeModel(settings.LLM_REASONING_MODEL)


def _strip_json(raw: str) -> str:
    """Pull a JSON object/array out of an LLM response (handles ```json fences)."""
    if not raw:
        return ""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]
    return raw.strip()


@retry(wait=wait_exponential(multiplier=1, min=2, max=15), stop=stop_after_attempt(3))
def _generate_json(prompt: str) -> dict:
    with timer() as t:
        resp = _model.generate_content(
            prompt,
            generation_config={"temperature": 0.0, "response_mime_type": "application/json"},
        )
    record_llm_call(
        "extract_json", settings.LLM_FAST_MODEL, t["ms"], usage_from_response(resp)
    )
    text = getattr(resp, "text", "") or ""
    try:
        return json.loads(_strip_json(text))
    except (json.JSONDecodeError, TypeError):
        return {}


def extract_symptom_tags(markdown: str, category: str) -> list[str]:
    """
    Extract a short list of normalized symptom tags from a repair guide page.
    e.g. ["not making ice", "water not dispensing"].
    """
    if not settings.ENABLE_LLM_EXTRACTION or not markdown:
        return []
    prompt = (
        "You are tagging an appliance repair guide for search filtering.\n"
        f"Appliance category: {category}.\n"
        "From the page content below, return STRICT JSON of the form "
        '{"symptoms": ["...", "..."]} where each item is a short, lowercase '
        "symptom phrase a customer might type (max 8 tags, no duplicates).\n\n"
        f"CONTENT:\n{markdown[:6000]}"
    )
    data = _generate_json(prompt)
    tags = data.get("symptoms", []) if isinstance(data, dict) else []
    return [str(t).strip().lower() for t in tags if str(t).strip()][:8]


def extract_part_details(markdown: str, category: str) -> dict:
    """
    Extract structured part fields from a part page's markdown.
    Returns keys: description, fixes_symptoms, compatible_models,
    installation_steps, price, in_stock, part_name.
    """
    empty = {
        "description": "",
        "fixes_symptoms": [],
        "compatible_models": [],
        "installation_steps": [],
        "price": "",
        "in_stock": None,
        "part_name": "",
    }
    if not settings.ENABLE_LLM_EXTRACTION or not markdown:
        return empty

    prompt = (
        "Extract structured data about a single appliance replacement part from "
        "the page content. Return STRICT JSON with EXACTLY these keys:\n"
        '{"part_name": str, "description": str, '
        '"fixes_symptoms": [str], "compatible_models": [str], '
        '"installation_steps": [str], "price": str, "in_stock": bool}\n'
        "Rules: fixes_symptoms = short lowercase symptom phrases this part "
        "resolves. compatible_models = model numbers (uppercase) the part fits "
        "(max 25). price = number only if shown. Use [] or \"\" when unknown.\n\n"
        f"Appliance category: {category}\nCONTENT:\n{markdown[:8000]}"
    )
    data = _generate_json(prompt)
    if not isinstance(data, dict):
        return empty

    def _list(key, cap):
        vals = data.get(key, []) or []
        if not isinstance(vals, list):
            return []
        return [str(v).strip() for v in vals if str(v).strip()][:cap]

    return {
        "description": str(data.get("description", "") or "")[:1000],
        "fixes_symptoms": [s.lower() for s in _list("fixes_symptoms", 10)],
        "compatible_models": [m.upper() for m in _list("compatible_models", 25)],
        "installation_steps": _list("installation_steps", 12),
        "price": str(data.get("price", "") or ""),
        "in_stock": data.get("in_stock", None),
        "part_name": str(data.get("part_name", "") or ""),
    }


@retry(wait=wait_exponential(multiplier=1, min=2, max=15), stop=stop_after_attempt(2))
def _generate_text(prompt: str, model) -> str:
    with timer() as t:
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": 0.3},
        )
    record_llm_call(
        "synthesize",
        getattr(model, "model_name", settings.LLM_FAST_MODEL),
        t["ms"],
        usage_from_response(resp),
    )
    return (getattr(resp, "text", "") or "").strip()


def plan_discovery(goal: str, signals: dict) -> dict:
    """AGENTIC PLANNER — decide WHICH PartSelect pages to fetch for a goal.

    This is the step that makes scraping "agentic" rather than a fixed recipe:
    instead of always crawling the same seed URLs, the LLM looks at the user's
    goal plus extracted signals (model number, brand, category, part name,
    symptom) and proposes an ORDERED set of high-level page *types* to open.

    It returns only abstract targets — never raw URLs — so the engine stays in
    control of URL construction (templates) and link discovery (live, off the
    page). Returns a dict like::

        {"targets": [
            {"type": "model", "reason": "user gave model WRF560SEHZ00"},
            {"type": "repair", "value": "ice maker", "reason": "symptom match"},
            {"type": "search", "value": "ice maker", "reason": "fallback"}
        ]}

    ``type`` is one of: model | repair | brand | category | search.
    Degrades to a single search target on any failure so discovery always has a
    valid door in.
    """
    fallback = {"targets": [{"type": "search", "value": goal, "reason": "default"}]}
    if not settings.ENABLE_LLM_EXTRACTION or not goal.strip():
        return fallback

    prompt = (
        "You are the planning brain of an agentic web scraper for PartSelect "
        "(Refrigerator & Dishwasher parts only). Decide which page TYPES to "
        "fetch to satisfy the user's goal, in priority order.\n\n"
        "Allowed target types:\n"
        "- model: the appliance model page (use when a model number is known)\n"
        "- repair: a symptom repair guide (value = short symptom phrase)\n"
        "- brand: a brand parts page (value = brand name)\n"
        "- category: a part-type listing (value = part type, e.g. 'ice maker')\n"
        "- search: PartSelect site search (value = query) — always valid\n\n"
        "Rules: propose 1-3 targets, most useful first. Prefer the most specific "
        "door available (model > repair/category > brand > search). Always "
        "include a search target last as a safety net. Return STRICT JSON: "
        '{"targets":[{"type":..., "value":..., "reason":...}]}.\n\n'
        f"GOAL: {goal}\n"
        f"SIGNALS: model={signals.get('model_number') or '-'}, "
        f"brand={signals.get('brand') or '-'}, "
        f"category={signals.get('category') or '-'}, "
        f"part_name={signals.get('part_name') or '-'}, "
        f"symptom={signals.get('symptom') or '-'}\n"
    )
    data = _generate_json(prompt)
    targets = data.get("targets") if isinstance(data, dict) else None
    if not isinstance(targets, list) or not targets:
        return fallback
    clean: list[dict] = []
    for t in targets[:3]:
        if not isinstance(t, dict):
            continue
        ttype = str(t.get("type", "")).strip().lower()
        if ttype not in {"model", "repair", "brand", "category", "search"}:
            continue
        clean.append(
            {
                "type": ttype,
                "value": str(t.get("value", "") or "").strip(),
                "reason": str(t.get("reason", "") or "").strip(),
            }
        )
    return {"targets": clean} if clean else fallback


def replan_discovery(goal: str, signals: dict, tried: list[str], found: str) -> dict | None:
    """AGENTIC REFLECTION — reason over the first pass and propose ONE more door.

    This is the "evaluate my own result and try again" step that makes the
    scraper iterative rather than single-shot. Given the goal, what door TYPES
    were already tried, and a short summary of what was found, the LLM proposes
    a single new, more-specific target to try next (or returns None if another
    attempt is unlikely to help).

    Returns a single target dict ``{"type", "value", "reason"}`` or None.
    """
    if not settings.ENABLE_LLM_EXTRACTION:
        return None
    prompt = (
        "You are the reflection step of an agentic scraper for PartSelect. A "
        "first discovery pass did NOT find a relevant replacement part. Decide "
        "the single best NEXT door to try, or whether to stop.\n\n"
        "Allowed target types: model, repair, brand, category, search.\n"
        "Guidance: if a broad door was tried, get more specific (e.g. a precise "
        "'category' part-type or a tighter 'search' query that names the exact "
        "part + appliance). Don't repeat a door that already failed unless you "
        "materially change its value.\n\n"
        f"GOAL: {goal}\n"
        f"SIGNALS: model={signals.get('model_number') or '-'}, "
        f"brand={signals.get('brand') or '-'}, "
        f"category={signals.get('category') or '-'}, "
        f"part_name={signals.get('part_name') or '-'}, "
        f"symptom={signals.get('symptom') or '-'}\n"
        f"ALREADY TRIED: {', '.join(tried) or 'none'}\n"
        f"FOUND SO FAR: {found or 'nothing relevant'}\n\n"
        'Return STRICT JSON: {"next": {"type":..., "value":..., "reason":...}} '
        'or {"next": null} to stop.'
    )
    data = _generate_json(prompt)
    nxt = data.get("next") if isinstance(data, dict) else None
    if not isinstance(nxt, dict):
        return None
    ttype = str(nxt.get("type", "")).strip().lower()
    if ttype not in {"model", "repair", "brand", "category", "search"}:
        return None
    return {
        "type": ttype,
        "value": str(nxt.get("value", "") or "").strip(),
        "reason": str(nxt.get("reason", "") or "").strip(),
    }


def rank_links(goal: str, candidates: list[dict], limit: int) -> list[str]:
    """AGENTIC RANKER — score discovered links by relevance to the goal.

    The page yields many candidate links (regex finds them all). Rather than
    blindly taking the first N (today's behavior), the LLM picks the ``limit``
    most relevant URLs for the goal — e.g. the ice-maker parts, not whatever 20
    links appeared first. ``candidates`` is a list of ``{"url", "label"}``.

    Returns an ordered list of URLs (subset of the inputs). Degrades to the
    first ``limit`` candidates if the LLM is unavailable or returns garbage, so
    discovery still makes progress.
    """
    urls = [c.get("url", "") for c in candidates if c.get("url")]
    if not urls:
        return []
    fallback = urls[:limit]
    if not settings.ENABLE_LLM_EXTRACTION:
        return fallback

    # Index the candidates so the LLM can reference them compactly by number,
    # keeping the prompt small (URLs are long and burn tokens).
    listing = "\n".join(
        f"{i}. {c.get('label') or ''} -> {c.get('url')}"
        for i, c in enumerate(candidates)
        if c.get("url")
    )
    prompt = (
        "You are ranking candidate PartSelect links by how relevant each is to "
        "the user's goal. Pick ONLY the links that genuinely help; ignore "
        "cross-sell, navigation, and unrelated parts.\n\n"
        f"GOAL: {goal}\n\n"
        f"CANDIDATES (index. label -> url):\n{listing}\n\n"
        f"Return STRICT JSON {{\"picks\":[<indices>]}} with at most {limit} "
        "indices, most relevant first. Return [] if none are relevant."
    )
    data = _generate_json(prompt)
    picks = data.get("picks") if isinstance(data, dict) else None
    if not isinstance(picks, list) or not picks:
        return fallback
    chosen: list[str] = []
    for p in picks:
        try:
            idx = int(p)
        except (ValueError, TypeError):
            continue
        if 0 <= idx < len(candidates):
            url = candidates[idx].get("url")
            if url and url not in chosen:
                chosen.append(url)
        if len(chosen) >= limit:
            break
    return chosen or fallback


def synthesize_answer(user_message: str, intent: str, context: str) -> str:
    """
    Use the strong reasoning model to write the final chat answer from retrieved
    context. Returns "" when synthesis is disabled or fails (caller falls back to
    the deterministic template).
    """
    if not settings.ENABLE_LLM_SYNTHESIS or not context.strip():
        return ""

    prompt = (
        "You are the PartSelect assistant for Refrigerator and Dishwasher parts "
        "only. Answer the customer's question using ONLY the context below. Be "
        "concise, accurate, and helpful. Never invent part numbers, prices, or "
        "compatibility. Never ask for payment or login details. If you don't "
        "have enough information to answer, do NOT mention 'context', "
        "'provided', or any internal/source wording — simply say you don't have "
        "a specific guide for that yet and suggest checking PartSelect for their "
        "model.\n\n"
        "FORMATTING RULES (Markdown):\n"
        "- Open with one short sentence (no heading).\n"
        "- Keep the whole reply under ~120 words.\n"
        "- If you list details or steps, put EACH item on its own line as a "
        "Markdown bullet starting with '- ' (a hyphen and a space). Never put "
        "multiple bullets on the same line.\n"
        "- You may bold a short label with **Label:** at the start of a bullet.\n"
        "- Do not wrap the answer in code fences. Do not add a closing summary.\n\n"
        f"Customer question: {user_message}\n"
        f"Detected intent: {intent}\n\n"
        f"Context:\n{context[:8000]}\n\n"
        "Answer:"
    )
    try:
        # Use the fast model for synthesis: it summarizes already-retrieved
        # context, so Flash is ~2-3x faster than Pro with comparable quality.
        return _generate_text(prompt, _model)
    except Exception:
        return ""
