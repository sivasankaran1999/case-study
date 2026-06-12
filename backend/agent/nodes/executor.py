"""Executor node: dispatches to tools based on routed intent."""

import json

from agent.state import AgentState
from agent.utils import (
    REPAIR_RE,
    dedupe_parts,
    enrich_search_query,
    format_part_from_metadata,
    is_followup_reference,
    is_problem_followup,
)
from config.settings import settings
from rag.self_heal import get_model_compatible_parts
from tools import TOOL_REGISTRY
from tools.get_order_links import (
    get_part_order_link,
    get_order_status_link,
    get_returns_link,
)


def _inherited_problem_query(message: str, category: str, slots: dict) -> str | None:
    """Query anchored on the REMEMBERED symptom for a vague problem follow-up.

    After "my fridge isn't cooling", a bare "what part do I need?" carries no
    searchable terms of its own. Rather than searching that literal text (which
    matches unrelated content), we reuse the stored symptom + category so the
    retrieval stays on the actual problem. Returns None when there's no stored
    symptom or the message stands on its own.
    """
    last_symptom = (slots or {}).get("last_symptom")
    if last_symptom and is_problem_followup(message):
        return enrich_search_query(last_symptom, category)
    return None


def _repair_query(message: str, category: str, slots: dict) -> str:
    """Build the repair-guide retrieval query.

    Prefers the concrete symptom over the full verbose message — a model number
    and brand ("My Whirlpool WRF560SEHZ00 fridge isn't cooling") dilute the
    embedding and mis-rank the guide. Falls back to the remembered symptom for a
    contextless follow-up, then to the raw message.
    """
    m = REPAIR_RE.search(message or "")
    if m:
        return enrich_search_query(m.group(0), category)
    return _inherited_problem_query(message, category, slots) or enrich_search_query(
        message, category
    )


def _search_query(message: str, category: str, slots: dict, clean_query: str = "") -> str:
    """Build the part-search query.

    Prefers Flash's filler-free ``clean_search_query`` (e.g. "Temperature
    Sensor" instead of "Find a Temperature Sensor for this model please"). When
    that's empty, falls back to: the remembered part name for a referential
    follow-up ("how do I install it"), then the remembered symptom for a vague
    problem follow-up ("what part do I need?"), then the raw message — so the
    user never has to repeat what they just told us.
    """
    if clean_query:
        return enrich_search_query(clean_query, category)
    last_name = (slots or {}).get("last_part_name")
    if last_name and is_followup_reference(message):
        return enrich_search_query(f"{last_name} {message}", category)
    inherited = _inherited_problem_query(message, category, slots)
    if inherited:
        return inherited
    return enrich_search_query(message, category)


def _discovery_signals(state: dict, slots: dict, category: str) -> dict:
    """Assemble the slot signals the agentic planner uses to pick entry doors.

    Pulls from both the live turn state and remembered slot memory so a goal
    like "what part do I need?" still carries the model/brand/symptom the user
    mentioned earlier.
    """
    slots = slots or {}
    return {
        "model_number": state.get("model_number") or slots.get("last_model") or "",
        "brand": slots.get("brand") or "",
        "category": category or "",
        "part_name": slots.get("last_part_name") or "",
        "symptom": slots.get("last_symptom") or "",
    }


def _agentic_recover(
    goal: str, signals: dict, requery: str, namespace: str, search_rag
) -> tuple[list[dict], dict | None]:
    """On a hard search miss, run agentic discovery then re-query Pinecone ONCE.

    Strictly additive recovery layer: it only runs when ENABLE_AGENTIC_DISCOVERY
    is on AND the normal retrieval already came back empty, so the default path
    and its latency are untouched. The discovery tool upserts any newly found
    parts, then we re-query the same namespace to pick them up at Tier 1.

    Returns (relevant_hits, discovery_report). Never raises — any failure
    degrades to the original empty result so the existing self-heal/clarify flow
    still takes over.

    MODEL-AWARE: only runs when a model number is known. With a model, discovery
    opens the model page and finds the EXACT compatible parts (precise, high
    value). Without one it can only fall back to generic landing/search pages,
    which tend to index loosely-related parts — so we skip it and let the normal
    clarify flow ask for the model instead.
    """
    if not settings.ENABLE_AGENTIC_DISCOVERY or not goal.strip():
        return [], None
    if not (signals or {}).get("model_number"):
        return [], None
    try:
        report = TOOL_REGISTRY["discover_and_index"](goal, signals)
        hits = search_rag(requery, namespace=namespace)
        relevant = [
            h for h in hits
            if float(h.get("confidence", 0.0)) >= settings.SEARCH_RELEVANCE_FLOOR
        ]
        return relevant, report
    except Exception as e:  # noqa: BLE001
        print(f"Agentic recovery failed: {e}")
        return [], None


def _annotate_fit(parts: list[dict], model_number: str, category: str) -> None:
    """Tag each part with a three-state fit signal against a known model:

      True       -> explicitly confirmed on the model's compatible-parts list.
      "verify"   -> not in the (incomplete) cache but in the same appliance
                    category; surfaced as a "verify on PartSelect" link rather
                    than a discouraging false negative.
      None / unset -> no basis to judge (no model saved, or no compatibility
                    data to reference) -> no badge shown.

    There is intentionally no blanket "does not fit" state — absence from the
    cache is not evidence of incompatibility.
    """
    if not model_number or not parts:
        return
    compat = get_model_compatible_parts(model_number, category)
    if compat is None:
        # No compatibility data to reference -> don't imply uncertainty.
        return
    for p in parts:
        pn = (p.get("part_number") or "").upper()
        if pn and pn in compat:
            p["fits_model"] = True
        elif category:
            # In-category but unconfirmed: let the user verify on PartSelect.
            p["fits_model"] = "verify"
        else:
            p["fits_model"] = None


def executor_node(state: AgentState) -> dict:
    intent = state.get("intent", "search")
    message = state.get("message", "")
    part_number = state.get("part_number") or ""
    model_number = state.get("model_number") or ""
    category = state.get("category") or ""
    slots = state.get("slots") or {}
    clean_query = state.get("clean_search_query") or ""

    # These intents need no tools — the synthesizer handles them directly.
    if intent in (
        "out_of_scope",
        "sensitive",
        "provide_model",
        "greeting",
        "intent_clarify",
        "clarify",
    ):
        return {"tool_results": []}

    tool_results: list[dict] = []
    parts: list[dict] = []
    order_url = None
    confidence = 0.0

    lookup_part = TOOL_REGISTRY["lookup_part"]
    check_compat = TOOL_REGISTRY["check_compatibility"]
    search_rag = TOOL_REGISTRY["search_rag"]
    get_repair = TOOL_REGISTRY["get_repair_guide"]
    lookup_error_code = TOOL_REGISTRY["lookup_error_code"]

    if intent in ("lookup_part", "install_help"):
        if part_number:
            result = lookup_part(part_number, category)
            tool_results.append({"tool": "lookup_part", "result": result})
            if result:
                parts.append(format_part_from_metadata(result))
                confidence = float(result.get("confidence", 0.85))
        else:
            search_q = _search_query(message, category, slots, clean_query)
            hits = search_rag(search_q, namespace=settings.NAMESPACE_PARTS)
            relevant = [
                h for h in hits
                if float(h.get("confidence", 0.0)) >= settings.SEARCH_RELEVANCE_FLOOR
            ]
            # On a hard miss, try agentic discovery (flag-gated) then re-query.
            if not relevant:
                goal = clean_query or message
                signals = _discovery_signals(state, slots, category)
                recovered, report = _agentic_recover(
                    goal, signals, search_q, settings.NAMESPACE_PARTS, search_rag
                )
                if report is not None:
                    tool_results.append({"tool": "discover_and_index", "result": report})
                if recovered:
                    relevant = recovered
            tool_results.append({"tool": "search_rag", "result": relevant})
            for hit in relevant:
                parts.append(format_part_from_metadata(hit.get("metadata", {})))
            if relevant:
                confidence = float(relevant[0].get("confidence", 0.0))

    elif intent == "compatibility":
        if part_number and model_number:
            result = check_compat(part_number, model_number, category)
            tool_results.append({"tool": "check_compatibility", "result": result})
            confidence = 0.95
            # Also surface the part card when we can resolve it quickly.
            part_meta = lookup_part(part_number, category)
            if part_meta:
                parts.append(format_part_from_metadata(part_meta))
        elif part_number and not model_number:
            # Known part, but no model to check against — ask for it.
            tool_results.append({
                "tool": "check_compatibility",
                "result": {
                    "error": "missing_model",
                    "message": (
                        f"I can check that for you. Which model should I verify "
                        f"{part_number} against? Share your appliance's model number "
                        "(usually on a sticker inside the door)."
                    ),
                },
            })
            part_meta = lookup_part(part_number, category)
            if part_meta:
                parts.append(format_part_from_metadata(part_meta))
        else:
            tool_results.append({
                "tool": "check_compatibility",
                "result": {
                    "error": "missing_entities",
                    "message": "Please provide both a part number (PS…) and a model number.",
                },
            })

    elif intent == "repair_guide":
        # A brand-specific fault code (e.g. "F8 E4", "E15", "OF OF") gets a
        # precise, grounded answer from the curated, brand-keyed error-code KB.
        # Fall back to the symptom-based repair guides for everything else. The
        # KB hit is shaped like a repair-guide hit, so the synthesizer +
        # RepairGuideCard render it unchanged.
        brand = (slots or {}).get("brand") or ""
        repair_hits = lookup_error_code(message, category, brand)
        if not repair_hits:
            repair_hits = get_repair(_repair_query(message, category, slots))
        repair_hits = [
            h for h in repair_hits
            if float(h.get("confidence", 0.0)) >= settings.SEARCH_RELEVANCE_FLOOR
        ]
        tool_results.append({"tool": "get_repair_guide", "result": repair_hits})
        if repair_hits:
            confidence = float(repair_hits[0].get("confidence", 0.0))
            for hit in repair_hits[:2]:
                meta = hit.get("metadata", {})
                rec = meta.get("recommended_parts", "[]")
                try:
                    rec_list = json.loads(rec) if isinstance(rec, str) else rec
                except (json.JSONDecodeError, TypeError):
                    rec_list = []
                for pn in (rec_list or [])[:3]:
                    part_meta = lookup_part(pn, category)
                    if part_meta:
                        parts.append(format_part_from_metadata(part_meta))

    elif intent == "order_placement":
        # Redirect only — no scrape; construct URL from part number directly.
        result = get_part_order_link(part_number, product_url=None)
        tool_results.append({"tool": "get_part_order_link", "result": result})
        order_url = result.get("url")
        confidence = 1.0

    elif intent == "order_status":
        result = get_order_status_link()
        tool_results.append({"tool": "get_order_status_link", "result": result})
        order_url = result.get("url")
        confidence = 1.0

    elif intent == "returns":
        # Redirect only — hand the user PartSelect's 365-day returns page.
        result = get_returns_link()
        tool_results.append({"tool": "get_returns_link", "result": result})
        order_url = result.get("url")
        confidence = 1.0

    else:  # search
        search_q = _search_query(message, category, slots, clean_query)
        part_hits = search_rag(search_q, namespace=settings.NAMESPACE_PARTS)
        part_hits = [
            h for h in part_hits
            if float(h.get("confidence", 0.0)) >= settings.SEARCH_RELEVANCE_FLOOR
        ]
        # On a hard part miss, try agentic discovery (flag-gated) then re-query.
        if not part_hits:
            goal = clean_query or message
            signals = _discovery_signals(state, slots, category)
            recovered, report = _agentic_recover(
                goal, signals, search_q, settings.NAMESPACE_PARTS, search_rag
            )
            if report is not None:
                tool_results.append({"tool": "discover_and_index", "result": report})
            if recovered:
                part_hits = recovered
        tool_results.append({"tool": "search_rag_parts", "result": part_hits})
        for hit in part_hits:
            parts.append(format_part_from_metadata(hit.get("metadata", {})))
        repair_hits = get_repair(_repair_query(message, category, slots))
        repair_hits = [
            h for h in repair_hits
            if float(h.get("confidence", 0.0)) >= settings.SEARCH_RELEVANCE_FLOOR
        ]
        if repair_hits:
            tool_results.append({"tool": "get_repair_guide", "result": repair_hits})
        if part_hits:
            confidence = float(part_hits[0].get("confidence", 0.0))
        elif repair_hits:
            confidence = float(repair_hits[0].get("confidence", 0.0))

    # Annotate model-fit uniformly for EVERY part card we return (exact lookup,
    # search, compatibility, repair recommendations). This is the single
    # authoritative fit signal — derived from the model's full parts list — so
    # the expanded card never disagrees with the clarify-list badge.
    _annotate_fit(parts, model_number, category)

    return {
        "tool_results": tool_results,
        "parts": dedupe_parts(parts),
        "confidence": confidence,
        "order_url": order_url,
    }
