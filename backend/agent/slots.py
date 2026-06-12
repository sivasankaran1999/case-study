"""Layer 3 of the hybrid router: conversation slot memory.

Slots persist everything the user has told us across the WHOLE conversation so
no node ever has to ask twice. The cardinal rule: a slot is NEVER overwritten
with an empty value. If the user gave their model number in turn 1, it is still
in the slots at turn 10.

The chat API is stateless per request — the frontend replays the message
history and the saved model number every turn — so we rebuild the slots each
turn by replaying the conversation oldest -> newest and then layering the
current turn's freshly-extracted entities on top. Because we always replay the
full history, information from early turns survives indefinitely.

Slot keys: model_number, brand, category, last_part_number, last_part_name,
last_symptom.
"""

import re

from agent.utils import (
    REPAIR_RE,
    _model_from_text,
    extract_part_number,
    infer_category,
    is_model_statement,
)

SLOT_KEYS = (
    "model_number",
    "brand",
    "category",
    "last_part_number",
    "last_part_name",
    "last_symptom",
)

# Brands PartSelect commonly carries for refrigerators / dishwashers.
_BRANDS = (
    "whirlpool", "ge", "frigidaire", "maytag", "kitchenaid", "samsung", "lg",
    "bosch", "kenmore", "amana", "electrolux", "jenn-air", "jennair", "haier",
    "magic chef", "admiral", "roper", "estate", "inglis", "kelvinator",
)
_BRAND_RE = re.compile(
    r"\b(" + "|".join(re.escape(b) for b in _BRANDS) + r")\b", re.IGNORECASE
)


def _set(slots: dict, key: str, value) -> None:
    """Fill a slot only with a non-empty value — never overwrite with empty."""
    if value is None:
        return
    v = value.strip() if isinstance(value, str) else value
    if v == "" or v is None:
        return
    slots[key] = v


def _brand_in(text: str) -> str:
    m = _BRAND_RE.search(text or "")
    return m.group(1).title() if m else ""


def _symptom_in(text: str) -> str:
    m = REPAIR_RE.search(text or "")
    return m.group(0).strip().lower() if m else ""


def build_slots(
    message: str,
    history,
    saved_model,
    flash_entities: dict | None = None,
    inferred_category: str | None = None,
) -> dict:
    """Rebuild the full slot memory for this turn.

    Order matters — later writes win, but only when non-empty:
      1. Replay conversation history oldest -> newest (rule extraction).
      2. The UI-remembered model number (persists across the session).
      3. The current message (rule extraction).
      4. The current message's Flash-extracted entities (richest signal).
      5. Flash's inferred category — only when no category is set yet.
    """
    slots: dict = {}

    # 1. Replay history. Category only from user turns — the assistant welcome
    # ("Refrigerator and Dishwasher parts") must not set a bogus category slot.
    for turn in (history or []):
        content = turn.get("content", "") or ""
        role = (turn.get("role") or "user").lower()
        _set(slots, "last_part_number", extract_part_number(content))
        _set(slots, "model_number", _model_from_text(content))
        if role == "user":
            _set(slots, "category", infer_category(content))
            _set(slots, "brand", _brand_in(content))
            _set(slots, "last_symptom", _symptom_in(content))

    # 2. Saved model from the UI header — authoritative across the session.
    if saved_model:
        _set(slots, "model_number", str(saved_model).upper().strip())

    # 3. Current message (rules).
    _set(slots, "last_part_number", extract_part_number(message))
    _set(slots, "category", infer_category(message))
    _set(slots, "brand", _brand_in(message))
    _set(slots, "last_symptom", _symptom_in(message))
    # A fresh model statement in this message overrides the saved one.
    if is_model_statement(message):
        _set(slots, "model_number", _model_from_text(message))

    # 4. Current message (Flash entities) — highest priority for this turn.
    if flash_entities:
        _set(slots, "last_part_number", flash_entities.get("part_number"))
        _set(slots, "last_part_name", flash_entities.get("part_name"))
        _set(slots, "model_number", flash_entities.get("model_number"))
        _set(slots, "brand", flash_entities.get("brand"))
        _set(slots, "category", flash_entities.get("category"))
        _set(slots, "last_symptom", flash_entities.get("symptom"))

    # 5. Inferred category from a model number — only a fallback. Never
    # overwrite a category that was explicitly stated or already known.
    if inferred_category and not slots.get("category"):
        _set(slots, "category", inferred_category)

    return slots
