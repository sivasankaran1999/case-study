"""Layer 2 of the hybrid router: Gemini Flash intent classification.

The deterministic rule layer (see :mod:`agent.utils`) only handles the handful
of 100%-unambiguous messages. Everything else lands here. Flash reads the
current message, the last few conversation turns, and the slots we have already
filled, and returns a structured classification:

    - intent           (mapped onto the executor's intent vocabulary)
    - confidence       (0.0 - 1.0)
    - entities         (part number, part name, model, brand, symptom, category)
    - action           (what the user wants: buy / find / fix / check / install)
    - needs_clarification + one targeted clarification question

This is what lets the agent understand that "defrost thermostat" is a part name
(not a symptom), that "purchase a temperature sensor" means *find and buy* a
part (not checkout), and that "door basket" is a dishwasher part even though it
matches no keyword.
"""

import json
import re

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from observability import log_event, record_llm_call, timer, usage_from_response

# Flash's intent vocabulary -> the intents the executor / synthesizer expect.
INTENT_MAP = {
    "part_lookup": "lookup_part",
    "compatibility": "compatibility",
    "repair": "repair_guide",
    "install": "install_help",
    "order_status": "order_status",
    "order_placement": "order_placement",
    "returns": "returns",
    "search": "search",
    "greeting": "greeting",
    "provide_model": "provide_model",
    "out_of_scope": "out_of_scope",
}

_VALID_ACTIONS = {"buy", "find", "fix", "check", "install", "none"}
_VALID_CATEGORIES = {"refrigerator", "dishwasher", ""}

# Symptoms too generic to retrieve a useful repair guide from. On their own
# (no appliance/part context) these must trigger a clarifying question rather
# than a doomed repair-guide search (e.g. "it's broken", "not working").
_VAGUE_SYMPTOMS = {
    "broken", "not working", "doesn't work", "does not work", "won't work",
    "wont work", "not work", "issue", "problem", "stopped working", "help",
    "malfunctioning", "acting up", "no longer works", "isn't working",
}

# Confidence policy (three bands):
#   >= HIGH_CONFIDENCE          -> trust the intent and act directly, even if
#                                  the model wanted to ask a clarifying question.
#   CONFIDENCE_THRESHOLD .. HIGH -> honor the model's own clarification decision.
#   <  CONFIDENCE_THRESHOLD      -> never act; force one targeted clarification.
CONFIDENCE_THRESHOLD = 0.75
HIGH_CONFIDENCE = 0.90

# Lazily-initialised model so importing this module never requires a live key
# (the router falls back to rule-based routing when classification is
# unavailable).
_flash = None


def _model():
    global _flash
    if _flash is None:
        genai.configure(api_key=(settings.GEMINI_API_KEY or "").strip())
        _flash = genai.GenerativeModel(settings.LLM_FAST_MODEL)
    return _flash


_SYSTEM = (
    "You are the intent router for the PartSelect assistant, which ONLY helps "
    "with Refrigerator and Dishwasher parts: finding parts, checking "
    "compatibility, troubleshooting/repairs, installation help, and ordering.\n\n"
    "Classify the CURRENT user message. Use the recent conversation and the "
    "known facts for context, but classify what the user wants RIGHT NOW.\n\n"
    "Return STRICT JSON with EXACTLY these keys:\n"
    "{\n"
    '  "intent": one of ["part_lookup","compatibility","repair","install",'
    '"order_status","order_placement","returns","search","greeting",'
    '"provide_model","out_of_scope"],\n'
    '  "confidence": float between 0.0 and 1.0,\n'
    '  "entities": {\n'
    '    "part_number": PartSelect "PS" number if present else "",\n'
    '    "part_name": e.g. "defrost thermostat", "door basket", "water filter", else "",\n'
    '    "model_number": appliance model number if stated this turn, else "",\n'
    '    "brand": e.g. "Whirlpool", else "",\n'
    '    "symptom": a described PROBLEM like "not draining" / "leaking", else "",\n'
    '    "category": one of ["refrigerator","dishwasher",""]\n'
    "  },\n"
    '  "action": one of ["buy","find","fix","check","install","none"],\n'
    '  "clean_search_query": the meaningful search terms only (see SEARCH QUERY '
    'rules), else "",\n'
    '  "inferred_category": one of ["refrigerator","dishwasher",null] (see '
    "CATEGORY INFERENCE rules),\n"
    '  "needs_clarification": boolean,\n'
    '  "clarification_question": ONE short targeted question, else ""\n'
    "}\n\n"
    "CLASSIFICATION RULES:\n"
    "- A part NAME is NOT a symptom. \"Defrost Thermostat\", \"Drain Pump\", "
    "\"Water Filter\", \"Defrost Heater\" are PART NAMES (intent=part_lookup), "
    "even though they contain words like defrost/drain/filter. Only an actual "
    "described problem (\"it won't defrost\", \"not draining\", \"leaking\") is a "
    "symptom (intent=repair).\n"
    "- \"purchase\" / \"buy\" / \"find\" / \"get me a <part>\" means the user wants "
    "to FIND a part to buy. intent=part_lookup (or search if no specific part), "
    "action=buy. This is NEVER order_placement.\n"
    "- order_placement is ONLY an explicit checkout/cart action on a part "
    "already in context: \"add this to cart\", \"check out\", \"order this one\". "
    "action=buy by itself is NOT order_placement.\n"
    "- order_status is tracking an EXISTING order (\"where is my order\", an "
    "order number).\n"
    "- returns = the user wants to RETURN/send back a part, get a REFUND, "
    "cancel an order, or asks about the RETURN POLICY (\"I want to return "
    "this\", \"how do I get a refund\", \"what's your return policy\"). "
    "action=none.\n"
    "- compatibility = \"does X fit my model\", \"will this work with...\", \"is X "
    "compatible\"; action=check.\n"
    "- install = \"how do I install/replace <part>\"; action=install.\n"
    "- A short UI button phrase like \"Check compatibility\", \"Find a part\", "
    "\"Track my order\" is a conversational trigger for that intent, NOT a "
    "literal product search query.\n"
    "- out_of_scope = washers, dryers, ovens, ranges, microwaves, stoves, or "
    "anything that is not a refrigerator or dishwasher part.\n"
    "- greeting = a bare greeting or thanks with no request.\n"
    "- provide_model = the message is essentially just the user supplying their "
    "appliance model number.\n\n"
    "SEARCH QUERY (clean_search_query):\n"
    "- Extract ONLY the meaningful search terms by understanding the language — "
    "the part name, symptom, or problem description. Drop conversational filler "
    "like \"find a\", \"I need a\", \"can you help me locate\", \"for this model "
    "please\", \"can you please\", \"desperately\". Keep an appliance word "
    "(refrigerator/dishwasher) when the user mentions it.\n"
    "- Examples:\n"
    "  \"Find a Temperature Sensor for this model please\" -> \"Temperature Sensor\"\n"
    "  \"I desperately need a door basket for my dishwasher\" -> \"door basket dishwasher\"\n"
    "  \"can you help me find a defrost thermostat\" -> \"defrost thermostat\"\n"
    "  \"my ice maker stopped working\" -> \"ice maker not working\"\n"
    "  \"I need help with leaking\" -> \"leaking\"\n"
    "- Leave \"\" when there are no product/problem terms (e.g. a greeting).\n\n"
    "CATEGORY INFERENCE (inferred_category):\n"
    "- If a model number is present in the message OR in the known facts, "
    "confidently infer whether it is a refrigerator or dishwasher from known "
    "model-number patterns. E.g. GE models like GFSS2HCYCSS are refrigerators; "
    "Whirlpool dishwasher models typically start with WD (e.g. WDT780SAEM1).\n"
    "- If you cannot confidently infer it, set inferred_category to null — do "
    "NOT guess.\n\n"
    "CLARIFICATION:\n"
    "- Set needs_clarification=true ONLY when you cannot confidently pick an "
    "intent OR a critical entity is missing AND cannot be inferred from the "
    "known facts. Then ask EXACTLY ONE short question (e.g. \"Is this for your "
    "refrigerator or dishwasher?\"). NEVER ask for anything already listed in "
    "the known facts. Never ask more than one question.\n"
)


def _format_history(history, max_turns: int = 6) -> str:
    turns = (history or [])[-max_turns:]
    if not turns:
        return "(none)"
    lines = []
    for t in turns:
        role = t.get("role", "user")
        content = (t.get("content", "") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) or "(none)"


def _format_slots(slots: dict) -> str:
    known = {k: v for k, v in (slots or {}).items() if v}
    return json.dumps(known) if known else "(none)"


def _build_prompt(message: str, history, slots: dict) -> str:
    return (
        f"{_SYSTEM}\n"
        f"KNOWN FACTS (already told to us — never ask for these again):\n"
        f"{_format_slots(slots)}\n\n"
        f"RECENT CONVERSATION:\n{_format_history(history)}\n\n"
        f"CURRENT MESSAGE:\n{message}\n\n"
        "JSON:"
    )


def _strip_json(raw: str) -> str:
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


@retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(2))
def _generate(prompt: str) -> str:
    with timer() as t:
        resp = _model().generate_content(
            prompt,
            generation_config={
                "temperature": 0.0,
                "response_mime_type": "application/json",
            },
        )
    record_llm_call(
        "classify", settings.LLM_FAST_MODEL, t["ms"], usage_from_response(resp)
    )
    return getattr(resp, "text", "") or ""


def _clarification_for_missing(entities: dict) -> str:
    """Build one targeted question based on the most important missing entity.

    Used when confidence is too low to act and the model didn't supply its own
    clarification question.
    """
    has_part = bool(entities.get("part_number") or entities.get("part_name"))
    has_category = bool(entities.get("category"))
    has_symptom = bool(entities.get("symptom"))

    # Know what the part/problem is but not the appliance -> ask the appliance.
    if (has_part or has_symptom) and not has_category:
        return "Is this for your refrigerator or dishwasher?"
    # Know the appliance but nothing concrete to act on -> ask what they need.
    if has_category and not (has_part or has_symptom):
        return (
            f"What would you like help with on your {entities['category']} — "
            "finding a part, checking a fit, or fixing a problem?"
        )
    # Nothing usable at all.
    return (
        "Could you tell me a bit more — which part or problem, and is it for "
        "your refrigerator or dishwasher?"
    )


def _normalize(data: dict) -> dict:
    """Coerce raw model output into a safe, predictable shape."""
    raw_entities = data.get("entities") or {}
    category = str(raw_entities.get("category", "") or "").strip().lower()
    if category not in _VALID_CATEGORIES:
        category = ""

    entities = {
        "part_number": str(raw_entities.get("part_number", "") or "").strip().upper(),
        "part_name": str(raw_entities.get("part_name", "") or "").strip(),
        "model_number": str(raw_entities.get("model_number", "") or "").strip().upper(),
        "brand": str(raw_entities.get("brand", "") or "").strip(),
        "symptom": str(raw_entities.get("symptom", "") or "").strip().lower(),
        "category": category,
    }

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    action = str(data.get("action", "none") or "none").strip().lower()
    if action not in _VALID_ACTIONS:
        action = "none"

    intent = str(data.get("intent", "") or "").strip().lower()
    if intent not in INTENT_MAP:
        intent = "search"

    clean_search_query = str(data.get("clean_search_query", "") or "").strip()

    inferred_category = str(data.get("inferred_category", "") or "").strip().lower()
    if inferred_category not in ("refrigerator", "dishwasher"):
        inferred_category = None

    needs_clarification = bool(data.get("needs_clarification", False))
    clarification_question = str(data.get("clarification_question", "") or "").strip()

    # Apply the confidence policy.
    if confidence >= HIGH_CONFIDENCE:
        # High confidence: trust the classification and act directly instead of
        # interrupting with a question (e.g. "Defrost Thermostat" -> look it up).
        needs_clarification = False
        clarification_question = ""
    elif confidence < CONFIDENCE_THRESHOLD and not needs_clarification:
        # Low confidence: never act — force one targeted clarifying question,
        # generating one from the missing entity if the model didn't supply it.
        needs_clarification = True
        if not clarification_question:
            clarification_question = _clarification_for_missing(entities)

    return {
        "intent": intent,
        "confidence": confidence,
        "entities": entities,
        "action": action,
        "clean_search_query": clean_search_query,
        "inferred_category": inferred_category,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
    }


def classify(message: str, history, slots: dict) -> dict | None:
    """Classify ``message`` with Gemini Flash.

    Returns the normalized classification dict, or ``None`` if the classifier is
    unavailable (no API key) or the call fails. The router treats ``None`` as a
    clarification request — it never falls back to keyword/regex routing.
    """
    if not (settings.GEMINI_API_KEY or "").strip():
        return None
    try:
        raw = _generate(_build_prompt(message, history, slots))
    except Exception:
        return None
    try:
        data = json.loads(_strip_json(raw))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    result = _normalize(data)

    # Deterministic guards against Flash's non-deterministic overconfidence on
    # vague input (it flip-flops between clarify and act across identical calls).
    e = result["entities"]
    s = slots or {}

    if result["intent"] in ("part_lookup", "search") and not result["needs_clarification"]:
        # A part search needs a concrete target. With no part number, part name,
        # or symptom this turn AND none persisted in slots (e.g. "I need a
        # part"), force one clarifying question regardless of confidence.
        has_target = any(
            (
                e.get("part_number"),
                e.get("part_name"),
                e.get("symptom"),
                s.get("last_part_number"),
                s.get("last_part_name"),
                s.get("last_symptom"),
            )
        )
        if not has_target:
            result["needs_clarification"] = True
            result["clarification_question"] = (
                result["clarification_question"] or _clarification_for_missing(e)
            )

    elif result["intent"] == "repair" and not result["needs_clarification"]:
        # A repair needs a concrete symptom. A missing or too-generic symptom
        # ("it's broken", "not working") with no appliance context can't match a
        # useful guide -> clarify instead of running a doomed repair search.
        symptom = (e.get("symptom") or "").strip().lower()
        has_category = bool(e.get("category") or s.get("category"))
        actionable_symptom = symptom and symptom not in _VAGUE_SYMPTOMS
        if not actionable_symptom and not has_category:
            result["needs_clarification"] = True
            result["clarification_question"] = (
                result["clarification_question"]
                or "What's going wrong, and is it your refrigerator or dishwasher?"
            )

    log_event(
        "intent_classified",
        intent=result["intent"],
        confidence=result["confidence"],
        action=result["action"],
        needs_clarification=result["needs_clarification"],
        category=result["entities"].get("category") or None,
    )
    return result
