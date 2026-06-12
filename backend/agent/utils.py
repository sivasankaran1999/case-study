"""Shared helpers for routing, entity extraction, and response formatting."""

import json
import re
from typing import Any

PART_RE = re.compile(r"\b(PS\d+)\b", re.IGNORECASE)
# Common PartSelect model numbers: mixed alphanumeric, often 8–15 chars.
MODEL_RE = re.compile(r"\b([A-Z][A-Z0-9]{6,14})\b")

OUT_OF_SCOPE_APPLIANCES = (
    "washing machine", "washer", "dryer", "oven", "range", "microwave", "stove",
    "cooktop", "lawn mower", "lawnmower", "air conditioner", "furnace", "blender",
    "toaster", "coffee maker", "vacuum",
    # Clearly unrelated domains people sometimes ask about.
    "car", "vehicle", "truck", "phone", "laptop", "computer", "tv",
    "television", "garbage disposal", "water heater",
)

ORDER_STATUS_RE = re.compile(
    r"order\s*status|track(ing)?\s*(my\s*)?(order|package|shipment)|"
    r"where('?s|\s+is|\s+are)\s+my\s+(order|package|stuff|item)|"
    r"check\s+my\s+order|shipment\s+status|delivery\s+status|"
    r"when\s+will\s+(my|it).*(arrive|ship|come)",
    re.IGNORECASE,
)
ORDER_PLACEMENT_RE = re.compile(
    r"\b(order|buy|purchase|checkout|check\s+out)\b|"
    r"add\b[\w\s]*\bto\s+(cart|basket)|\bto\s+cart\b|add\s+to\s+cart|"
    r"get\s+(this|that|the)\s+part",
    re.IGNORECASE,
)
# Cart/checkout on a part already in context — needs a resolved PS number.
ORDER_CART_RE = re.compile(
    r"add\b[\w\s]*\bto\s+(cart|basket)|\bto\s+cart\b|add\s+to\s+cart|"
    r"checkout|check\s+out|get\s+(this|that)\s+part|order\s+(this|that)\b",
    re.IGNORECASE,
)
ORDER_VERB_RE = re.compile(r"\b(order|buy|purchase)\b", re.IGNORECASE)
# A message that is essentially the user supplying their appliance model number.
# Two phrasings: model-last ("my model is WRF535SWHZ") and model-first
# ("WRF535SWHZ is my model" / "MFI2568AES this is my model").
MODEL_STATEMENT_RE = re.compile(
    r"^\s*(here\s+is\s+|this\s+is\s+|here'?s\s+)?"
    r"(my\s+model(\s+(number|no\.?))?(\s+is)?\s+|"
    r"model(\s+(number|no\.?))?\s*(is\s+)?[:=]?\s*|"
    r"it'?s\s+(a\s+)?|i\s+have\s+(a\s+)?)?"
    r"[A-Z][A-Z0-9]{6,14}\s*$",
    re.IGNORECASE,
)
MODEL_STATEMENT_FIRST_RE = re.compile(
    r"^\s*[A-Z][A-Z0-9]{6,14}\s+"
    r"((this\s+)?is\s+(my|the)\s+model(\s+(number|no\.?))?|"
    r"my\s+model(\s+(number|no\.?))?)\s*$",
    re.IGNORECASE,
)
# Simple greetings / pleasantries with no actionable request.
GREETING_RE = re.compile(
    r"^\s*(hi|hey|hello|yo|hiya|howdy|good\s+(morning|afternoon|evening)|"
    r"greetings|sup|what'?s\s+up)[\s!.,?]*$",
    re.IGNORECASE,
)
# Thanks / acknowledgements that don't need a search.
THANKS_RE = re.compile(
    r"^\s*(thanks?|thank\s+you|thx|ty|ok(ay)?|cool|great|awesome|got\s+it|"
    r"perfect|nice|appreciate\s+it|cheers)[\s!.,?]*$",
    re.IGNORECASE,
)
# Sensitive data the assistant must never solicit or process.
SENSITIVE_RE = re.compile(
    r"(?:\d[ -]*?){13,16}|\bcvv\b|\bcvc\b|\bpassword\b|\bpasscode\b|"
    r"\bssn\b|social\s+security|credit\s+card\s+number|debit\s+card",
    re.IGNORECASE,
)
# Prompt-injection / meta questions about the assistant itself.
META_INJECTION_RE = re.compile(
    r"system\s+prompt|ignore\s+(all\s+)?previous|ignore\s+(your\s+)?instructions|"
    r"disregard\s+(the\s+)?(above|previous)|reveal\s+your\s+(prompt|instructions)|"
    r"what\s+(are\s+your|is\s+your)\s+(instructions|rules|prompt|guidelines)|"
    r"who\s+made\s+you|what\s+model\s+are\s+you|are\s+you\s+(chatgpt|gpt|gemini|claude)|"
    r"jailbreak|developer\s+mode|act\s+as\s+(a\s+)?(dan|different)",
    re.IGNORECASE,
)
COMPAT_RE = re.compile(
    r"compatible|compatibility|will\s+it\s+fit|does\s+it\s+fit|"
    r"work\s+with|works?\s+with|fit\s+my|fits\s+my|go\s+with|"
    r"\bfit\b|\bfits\b|right\s+part\s+for|correct\s+part\s+for",
    re.IGNORECASE,
)
INSTALL_RE = re.compile(
    r"\binstall(ation|ing)?\b|how\s+to\s+replace|how\s+do\s+i\s+replace|"
    r"replace\s+this\s+part|put\s+in\s+the",
    re.IGNORECASE,
)
REPAIR_RE = re.compile(
    r"not\s+working|won'?t\s+\w+|leaking|noisy|not\s+making\s+ice|"
    r"not\s+draining|draining|drain\b|not\s+cleaning|too\s+warm|too\s+cold|"
    r"broken|fix\s+my|troubleshoot|repair\s+guide|how\s+to\s+fix|"
    r"spots?\b|spotting|smell|odou?r|"
    # \b avoids matching inside part names like "defrost thermostat".
    r"\bfrost\b|\bfrosting\b|\bfrozen\b|"
    r"not\s+cooling|not\s+dispensing|"
    # Negated auxiliaries: "isn't cooling", "aren't working", "didn't start",
    # "is not starting" — common symptom phrasing the bare "not X" missed.
    r"(?:is|are|was|were|does|do|did|has|have)\s*n'?t\s+\w+|"
    r"(?:is|are|was|were)\s+not\s+\w+|"
    r"doesn'?t\s+\w+|stopped\s+\w+",
    re.IGNORECASE,
)
# Referential phrases that point back to a part already in the conversation,
# e.g. "is it in stock?", "how do I install this?", "order that one".
FOLLOWUP_RE = re.compile(
    r"\b(it|its|it'?s|this|that|them|these|those|the part|same\s+part|"
    r"this\s+one|that\s+one|the\s+one)\b|"
    r"in\s+stock|how\s+much|the\s+price|price\b|cost\b|availability",
    re.IGNORECASE,
)
# A standalone new search/topic that should NOT inherit prior context.
NEW_TOPIC_RE = re.compile(
    r"\b(show|find|looking\s+for|need\s+a|other|another|different|instead|"
    r"what\s+about|how\s+about)\b",
    re.IGNORECASE,
)
# Clear "I want to buy/find this" phrasing — no need to ask what they want.
BUY_SIGNAL_RE = re.compile(
    r"\b(want|need|looking\s+for|buy|purchase|get\s+(a|an|the|some)|"
    r"show\s+me|find\b|search|browse|"
    r"suggest\s+me\s+parts?|parts?\s+for|for\s+(my|this)\b.*\bmodel)\b",
    re.IGNORECASE,
)
# Too vague to be a product/topic name — don't offer intent chips.
_NON_PRODUCT_TOPIC_RE = re.compile(
    r"^\s*(help|info|information|question|something|anything|part|parts|"
    r"problem|issue|broken)\s*$",
    re.IGNORECASE,
)


def extract_part_number(text: str) -> str | None:
    m = PART_RE.search(text or "")
    return m.group(1).upper() if m else None


def _model_from_text(text: str) -> str | None:
    """Pull the first plausible model number out of free text."""
    for m in MODEL_RE.finditer(text or ""):
        candidate = m.group(1).upper()
        if candidate.startswith("PS"):
            continue
        return candidate
    return None


def extract_model_number(text: str, saved_model: str | None = None) -> str | None:
    # An explicit model statement in THIS message overrides the saved header
    # model (e.g. user says "here is my model ABC123" after saving a different
    # one in the UI).
    if is_model_statement(text):
        stated = _model_from_text(text)
        if stated:
            return stated
    if saved_model:
        return saved_model.upper().strip()
    return _model_from_text(text)


def last_part_number_in_history(history: list[dict] | None) -> str | None:
    """Most recent PS number mentioned in the conversation (any role)."""
    for turn in reversed(history or []):
        pn = extract_part_number(turn.get("content", "") or "")
        if pn:
            return pn
    return None


def last_model_number_in_history(history: list[dict] | None) -> str | None:
    """Most recent model number mentioned in the conversation (any role)."""
    for turn in reversed(history or []):
        text = turn.get("content", "") or ""
        for m in MODEL_RE.finditer(text):
            candidate = m.group(1).upper()
            if candidate.startswith("PS"):
                continue
            return candidate
    return None


def is_followup_reference(message: str) -> bool:
    """True when the message refers back to a part already discussed
    (pronouns, "in stock?", "the price", install/order/compat without a new
    part) rather than starting a new product search."""
    text = message or ""
    if NEW_TOPIC_RE.search(text):
        return False
    return bool(
        FOLLOWUP_RE.search(text)
        or INSTALL_RE.search(text)
        or COMPAT_RE.search(text)
        or ORDER_PLACEMENT_RE.search(text)
    )


# A vague follow-up about the problem already described ("what part do I need?",
# "how do I fix it?", "what do you recommend?") that names no new symptom of its
# own. These must inherit the remembered symptom for retrieval — searching their
# literal text matches nothing useful.
PROBLEM_FOLLOWUP_RE = re.compile(
    r"what\s+part|which\s+part|"
    r"what\s+(?:do|should)\s+i\s+(?:need|replace|buy|get|order|use|do)|"
    r"how\s+(?:do|can|should)\s+i\s+fix|how\s+to\s+fix\b|"
    r"what'?s\s+wrong|what\s+causes|what\s+is\s+causing|"
    r"\bfix\s+(?:it|this|that)\b|\brepair\s+(?:it|this|that)\b|"
    r"what\s+(?:now|next)|what\s+do\s+you\s+(?:recommend|suggest)|"
    r"any\s+(?:ideas|suggestions)",
    re.IGNORECASE,
)


def is_problem_followup(message: str) -> bool:
    """True for a vague 'what do I do about the problem' question that names no
    new symptom of its own — it should inherit the remembered symptom."""
    text = message or ""
    if REPAIR_RE.search(text):
        return False  # message carries its own symptom; no inheritance needed
    return bool(PROBLEM_FOLLOWUP_RE.search(text))


def resolve_context(
    message: str,
    history: list[dict] | None,
    saved_model: str | None,
) -> tuple[str | None, str | None]:
    """Resolve the effective part and model numbers for this turn, inheriting
    from conversation history when the message is a contextual follow-up.

    A new PS number in the message always wins (topic switch). Otherwise, if the
    message references a prior part ("it", "install this", "is it in stock"),
    inherit the most recent part number from history.
    """
    part_number = extract_part_number(message)
    model_number = extract_model_number(message, saved_model)

    if not part_number and is_followup_reference(message):
        part_number = last_part_number_in_history(history)

    if not model_number:
        model_number = last_model_number_in_history(history)

    return part_number, model_number


_FILLER_PREFIX_RE = re.compile(
    r"^\s*(i\s+(want|need|am\s+looking\s+for|'?m\s+looking\s+for|would\s+like)"
    r"(\s+(a|an|the|some))?|"
    r"can\s+i\s+(get|have|find)(\s+(a|an|the))?|"
    r"do\s+you\s+(have|sell|carry)(\s+(a|an|any))?|"
    r"show\s+me(\s+(a|an|the|some))?|find\s+me(\s+(a|an|the))?|"
    r"looking\s+for(\s+(a|an|the))?|where\s+can\s+i\s+(get|find|buy)(\s+(a|an|the))?|"
    r"i'?m\s+looking\s+for(\s+(a|an|the))?)\s+",
    re.IGNORECASE,
)


def clean_search_query(message: str) -> str:
    """Strip conversational filler so the product terms drive the embedding.

    'I want a Door Basket' -> 'Door Basket'. Falls back to the original text if
    stripping would leave it empty.
    """
    text = (message or "").strip()
    cleaned = _FILLER_PREFIX_RE.sub("", text).strip(" ?.!")
    return cleaned or text


def enrich_search_query(message: str, category: str = "") -> str:
    """Cleaned query plus a category hint (refrigerator/dishwasher) to lift
    relevance for sparse, conversationally-phrased searches."""
    cleaned = clean_search_query(message)
    cat = category or infer_category(message)
    if cat and cat.lower() not in cleaned.lower():
        return f"{cleaned} {cat}".strip()
    return cleaned


def infer_category(text: str) -> str:
    t = (text or "").lower()
    has_dishwasher = "dishwasher" in t
    has_refrigerator = any(
        w in t for w in ("refrigerator", "fridge", "freezer", "ice maker", "icemaker", "ice-maker")
    )
    # Scope/boilerplate mentioning BOTH appliances (e.g. the welcome message) is
    # not a user picking one — return empty so we don't poison lookups.
    if has_dishwasher and has_refrigerator:
        return ""
    if has_dishwasher:
        return "dishwasher"
    if has_refrigerator:
        return "refrigerator"
    return ""


def is_out_of_scope(message: str) -> bool:
    text = (message or "").lower()
    # Word-boundary match so "car" doesn't fire on "cart"/"card", and "washer"
    # doesn't fire on "dishwasher".
    mentions_unsupported = any(
        re.search(rf"\b{re.escape(a)}\b", text) for a in OUT_OF_SCOPE_APPLIANCES
    )
    mentions_supported = any(
        w in text for w in ("refrigerator", "fridge", "dishwasher", "freezer", "ice maker")
    )
    has_part = bool(extract_part_number(message))
    return mentions_unsupported and not mentions_supported and not has_part


def contains_sensitive_data(message: str) -> bool:
    """True if the message contains payment/credential/PII patterns."""
    return bool(SENSITIVE_RE.search(message or ""))


def is_meta_or_injection(message: str) -> bool:
    """True for prompt-injection attempts or meta questions about the assistant
    (system prompt, 'ignore previous instructions', 'what model are you')."""
    return bool(META_INJECTION_RE.search(message or ""))


def topic_from_message(message: str) -> str:
    """Product-ish phrase after stripping filler, appliance category words, and
    any model number."""
    topic = clean_search_query(message or "")
    topic = MODEL_RE.sub("", topic)
    for word in ("refrigerator", "fridge", "freezer", "dishwasher", "ice maker"):
        topic = re.sub(rf"\b{re.escape(word)}\b", "", topic, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", topic).strip(" ,.-")


def needs_intent_clarify(
    message: str,
    part_number: str | None,
    model_number: str | None = None,
) -> bool:
    """True when the user named a part/topic but gave no clear action
    (buy vs fix vs compatibility). Only used as a fallback — clear verbs,
    symptoms, or an in-message model number route directly without asking."""
    if part_number:
        return False
    text = message or ""
    # If a model is known (stated now or saved earlier), we have enough context
    # to just search for the part and flag what fits — don't interrupt with the
    # buy/fix/compat chips. Those are only useful for cold, context-free queries.
    if model_number:
        return False
    if any(
        rx.search(text)
        for rx in (
            ORDER_STATUS_RE,
            ORDER_PLACEMENT_RE,
            COMPAT_RE,
            INSTALL_RE,
            REPAIR_RE,
            GREETING_RE,
            THANKS_RE,
        )
    ):
        return False
    if (
        is_model_statement(text)
        or contains_sensitive_data(text)
        or is_meta_or_injection(text)
        or is_out_of_scope(text)
        or BUY_SIGNAL_RE.search(text)
        or is_followup_reference(text)
    ):
        return False
    topic = topic_from_message(text)
    if len(topic) < 3 or _NON_PRODUCT_TOPIC_RE.match(topic):
        return False
    return True


def build_intent_options(topic: str, model_number: str = "") -> list[dict]:
    """Clickable action choices when intent is ambiguous."""
    topic = (topic or "this part").strip()
    model = (model_number or "").strip().upper()
    if model:
        compat_msg = f"Does {topic} fit my model {model}?"
    else:
        compat_msg = f"Does {topic} fit my model?"
    return [
        {
            "id": "buy",
            "label": "Find / buy this part",
            "description": "Search PartSelect for matching parts",
            "message": f"I want to find {topic}",
        },
        {
            "id": "repair",
            "label": "Fix a problem",
            "description": "Troubleshoot symptoms or get a repair guide",
            "message": f"How do I fix problems related to {topic}?",
        },
        {
            "id": "compat",
            "label": "Check compatibility",
            "description": "See if it fits your appliance model",
            "message": compat_msg,
        },
    ]


def is_order_placement_intent(message: str, part_number: str | None) -> bool:
    """True only when the user wants to check out a *specific* known part.

    'I want to purchase Temperature Sensor' is a part search, not checkout.
    'Buy PS11752778' or 'add this to cart' (after a part was discussed) is."""
    text = message or ""
    if not part_number:
        return False
    if ORDER_CART_RE.search(text):
        return True
    if ORDER_VERB_RE.search(text) and (
        extract_part_number(text) or is_followup_reference(text)
    ):
        return True
    return False


def is_model_statement(message: str) -> bool:
    """True if the message is essentially just the user giving their model #
    (e.g. 'my model is WRF535SWHZ' or 'WRF535SWHZ this is my model') with no
    other request."""
    text = (message or "").strip()
    if not (MODEL_STATEMENT_RE.match(text) or MODEL_STATEMENT_FIRST_RE.match(text)):
        return False
    # Don't treat it as a bare statement if it also contains a part number or a
    # clear question/intent keyword.
    if extract_part_number(text):
        return False
    if any(
        rx.search(text)
        for rx in (COMPAT_RE, INSTALL_RE, REPAIR_RE, ORDER_PLACEMENT_RE)
    ):
        return False
    return True


def is_bare_part_number(message: str, part_number: str | None) -> bool:
    """True when the message is essentially just a PS part number (optionally
    with conversational filler like 'tell me about ...') and carries NO other
    intent signal. This is the only case where a PS number unambiguously means
    'look up this part' — anything else (compat, install, order, a symptom) is
    ambiguous and must go to the classifier."""
    if not part_number:
        return False
    text = message or ""
    if any(
        rx.search(text)
        for rx in (
            COMPAT_RE,
            INSTALL_RE,
            REPAIR_RE,
            ORDER_PLACEMENT_RE,
            ORDER_STATUS_RE,
        )
    ):
        return False
    return True


def is_order_status_only(message: str) -> bool:
    """True for an unambiguous order-tracking request with no part in play."""
    return bool(ORDER_STATUS_RE.search(message or "")) and not extract_part_number(message)


# Matches the executor's "missing_model" compatibility prompt so a bare model
# reply on the next turn can resume the check (see pending_compat_part).
_PENDING_COMPAT_RE = re.compile(
    r"which model should i verify\s+(PS\d+)", re.IGNORECASE
)


def pending_compat_part(history) -> str | None:
    """Return the part number the agent last asked the user to verify.

    When a compatibility request arrives with no model (e.g. "Does PS… fit my
    model?"), the executor replies asking for the model. If the user's next
    message is just that model number, it would otherwise be swallowed by the
    bare-model rule and acknowledged as "noted your model" — dropping the
    pending check. This inspects the most recent assistant turn; if it was that
    prompt, we return the part number so the router can resume compatibility.
    """
    for turn in reversed(history or []):
        role = (turn.get("role") or "").lower()
        if role != "assistant":
            continue
        match = _PENDING_COMPAT_RE.search(turn.get("content", "") or "")
        return match.group(1).upper() if match else None
    return None


# Model-number gate. Before recommending a NAMED part the user wants to find or
# buy (e.g. an ice maker), the router asks for the model number once. The lead
# phrase is fixed so a bare-model reply on the next turn can be detected, the
# remembered part recovered, and the search resumed — and so we never re-ask.
_MODEL_PROMPT_PREFIX = "Happy to help you find the right "
_MODEL_PROMPT_SUFFIX = (
    ". First — what's your appliance's model number? You can type it or upload a "
    "photo of the label, and I'll confirm the part actually fits your unit. "
    "(It's usually on a sticker inside the door, on the frame, or near the kickplate.)"
)
# Capture stops at ". First" to stay clear of apostrophes/dashes downstream.
_PENDING_MODEL_RE = re.compile(
    re.escape(_MODEL_PROMPT_PREFIX) + r"(.+?)\. First", re.IGNORECASE
)


def model_prompt_for(part: str) -> str:
    """The one-time 'what's your model number?' prompt for a named-part search."""
    return f"{_MODEL_PROMPT_PREFIX}{part}{_MODEL_PROMPT_SUFFIX}"


def pending_model_part(history) -> str | None:
    """Return the part the agent last asked a model number for (the model gate).

    Mirrors pending_compat_part: if the most recent assistant turn was the model
    gate prompt, return the part the user was looking for so the router can (a)
    resume the search when the next message is just a model number and (b) avoid
    asking for the model a second time. None when the last turn wasn't that
    prompt.
    """
    for turn in reversed(history or []):
        role = (turn.get("role") or "").lower()
        if role != "assistant":
            continue
        match = _PENDING_MODEL_RE.search(turn.get("content", "") or "")
        return match.group(1).strip() if match else None
    return None


def unambiguous_intent(message: str, part_number: str | None) -> str | None:
    """Layer 1 of the hybrid router: ONLY 100%-certain cases.

    Returns a routed intent for messages we can classify with complete
    certainty using simple rules, or ``None`` to defer to the Flash classifier.
    Never used for anything ambiguous.
    """
    # Safety always wins, regardless of anything else in the message.
    if contains_sensitive_data(message):
        return "sensitive"
    if is_meta_or_injection(message):
        return "out_of_scope"
    # Out-of-scope appliance (washer/dryer/oven/microwave/...) -> blocked.
    if is_out_of_scope(message):
        return "out_of_scope"
    # A bare greeting / thanks with nothing else is just a greeting.
    if GREETING_RE.match(message or "") or THANKS_RE.match(message or ""):
        return "greeting"
    # The message is essentially just the user supplying their model number.
    if is_model_statement(message):
        return "provide_model"
    # An order-tracking request with no part is order status.
    if is_order_status_only(message):
        return "order_status"
    # A PS number on its own always means part lookup.
    if is_bare_part_number(message, part_number):
        return "lookup_part"
    return None


def classify_intent(
    message: str,
    part_number: str | None,
    model_number: str | None,
) -> str:
    """Rule-based intent classification (fast, deterministic).

    Retained as the fallback path when the Flash classifier is unavailable.
    """
    # Safety first: never process payment/credential data.
    if contains_sensitive_data(message):
        return "sensitive"
    # Prompt-injection / meta questions -> politely refuse & redirect to scope.
    if is_meta_or_injection(message):
        return "out_of_scope"
    if is_out_of_scope(message):
        return "out_of_scope"
    # Greetings / thanks -> friendly conversational reply, no search.
    if GREETING_RE.match(message or "") or THANKS_RE.match(message or ""):
        return "greeting"
    # User just stating their model number -> acknowledge, don't search.
    if is_model_statement(message):
        return "provide_model"
    if ORDER_STATUS_RE.search(message):
        return "order_status"
    if is_order_placement_intent(message, part_number):
        return "order_placement"
    # Compatibility: trigger on a part + compat language even without a model
    # (the executor will ask for the model if it's missing).
    if COMPAT_RE.search(message) and part_number:
        return "compatibility"
    if INSTALL_RE.search(message) and part_number:
        return "install_help"
    if needs_intent_clarify(message, part_number, model_number):
        return "intent_clarify"
    if part_number and not REPAIR_RE.search(message):
        return "lookup_part"
    if REPAIR_RE.search(message):
        return "repair_guide"
    if part_number:
        return "lookup_part"
    return "search"


def parse_json_field(value: Any, default=None):
    if default is None:
        default = []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else default
        except (json.JSONDecodeError, TypeError):
            return default
    return default


def format_part_from_metadata(meta: dict) -> dict:
    """Map Pinecone / tool metadata to the frontend part card shape."""
    if not meta:
        return {}
    compat = parse_json_field(meta.get("compatible_models"), [])
    price = meta.get("price")
    if price is not None and price != "":
        try:
            price = float(str(price).replace("$", "").strip())
        except ValueError:
            price = None

    return {
        "part_number": meta.get("part_number", ""),
        "name": meta.get("part_name") or meta.get("name", ""),
        "price": price,
        "in_stock": bool(meta.get("in_stock", False)),
        "availability": meta.get("availability", "") or "",
        "image_url": meta.get("image_url", "") or "",
        "product_url": meta.get("url") or meta.get("product_url", "") or "",
        "compatible_with": compat,
        "description": meta.get("description", "") or "",
        "fixes_symptoms": parse_json_field(meta.get("fixes_symptoms"), []),
        "installation_steps": parse_json_field(meta.get("installation_steps"), []),
        "video_url": meta.get("video_url", "") or "",
    }


def _truncate_sentence(text: str, limit: int = 200) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return f"{cut}…"


def format_part_markdown(part: dict) -> str:
    """Deterministic, scannable markdown for part lookup replies."""
    name = part.get("name") or "Replacement Part"
    pn = part.get("part_number", "")
    lines = [f"**{name}** · `{pn}`", ""]

    desc = (part.get("description") or "").strip()
    if desc:
        lines.append(f"- **About:** {_truncate_sentence(desc)}")

    symptoms = part.get("fixes_symptoms") or []
    if symptoms:
        lines.append(f"- **Fixes:** {', '.join(symptoms[:4])}")

    steps = part.get("installation_steps") or []
    if steps:
        if len(steps) == 1:
            lines.append(f"- **Installation:** {steps[0]}")
        else:
            lines.append("- **Installation:**")
            for i, step in enumerate(steps[:4], 1):
                lines.append(f"  {i}. {step}")

    compat = part.get("compatible_with") or []
    if compat:
        shown = ", ".join(compat[:4])
        extra = f" (+{len(compat) - 4} more)" if len(compat) > 4 else ""
        lines.append(f"- **Fits:** {shown}{extra}")
    else:
        lines.append(
            "- **Compatibility:** Verify your model on PartSelect before ordering."
        )

    stock = part.get("in_stock")
    if stock is True:
        lines.append("- **Availability:** In stock — ships within one business day.")
    elif stock is False:
        lines.append("- **Availability:** Currently out of stock.")

    return "\n".join(lines)


def format_install_markdown(part: dict) -> str:
    """Markdown focused on installation steps."""
    name = part.get("name") or "this part"
    pn = part.get("part_number", "")
    steps = part.get("installation_steps") or []

    lines = [f"**How to install {name}** (`{pn}`)", ""]
    if steps:
        for i, step in enumerate(steps[:8], 1):
            lines.append(f"{i}. {step}")
    else:
        lines.append(
            "I don't have step-by-step instructions cached. "
            "Open the product page on PartSelect for videos and diagrams."
        )
    return "\n".join(lines)


def part_name_from_url(url: str) -> str:
    """Derive a readable part name from a PartSelect product URL slug.

    e.g. .../PS11739091-Whirlpool-WP2187172-Refrigerator-Door-Shelf-Bin-White.htm
    -> 'Refrigerator Door Shelf Bin White'
    """
    match = re.search(r"PS\d+-(.+?)\.htm", url or "", re.IGNORECASE)
    if not match:
        return ""
    slug = re.sub(r"-Part$", "", match.group(1), flags=re.IGNORECASE)
    words = slug.split("-")
    # First 1-2 tokens are usually brand + manufacturer number; drop them.
    if len(words) > 2 and re.search(r"\d", words[1]):
        words = words[2:]
    elif len(words) > 1 and re.fullmatch(r"[A-Z0-9]+", words[1] or ""):
        words = words[2:] if len(words) > 2 else words
    return " ".join(words).strip()


def display_name_for_part(part: dict) -> str:
    """Best-effort display name: stored name, else derived from the URL."""
    name = (part.get("name") or "").strip()
    if name:
        return name
    derived = part_name_from_url(part.get("product_url") or "")
    return derived or "Replacement Part"


def build_part_options(parts: list[dict], limit: int = 5) -> list[dict]:
    """Compact, clickable options for disambiguating a vague query.

    When parts carry a fits_model flag (a model is known), compatible parts are
    listed first and the flag is surfaced so the UI can badge them.
    """
    seen = set()
    deduped = []
    for p in parts:
        pn = (p.get("part_number") or "").upper()
        if not pn or pn in seen:
            continue
        seen.add(pn)
        deduped.append(p)

    # Stable sort: confirmed-fit first (True), in-category "verify" next,
    # unknown (None) last.
    def _fit_rank(p):
        fits = p.get("fits_model")
        if fits is True:
            return 0
        if fits == "verify":
            return 1
        return 2

    if any("fits_model" in p for p in deduped):
        deduped.sort(key=_fit_rank)

    options = []
    for p in deduped[:limit]:
        options.append(
            {
                "part_number": (p.get("part_number") or "").upper(),
                "name": display_name_for_part(p),
                "price": p.get("price"),
                "fits_model": p.get("fits_model"),
                "product_url": p.get("product_url") or "",
            }
        )
    return options


def dedupe_parts(parts: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for p in parts:
        pn = p.get("part_number", "")
        if pn and pn in seen:
            continue
        if pn:
            seen.add(pn)
        out.append(p)
    return out
