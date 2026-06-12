"""Input/output guardrails (scope + safety) for the agent.

Lightweight NeMo-style policy gateway. Two jobs:

1. Scope: keep the agent on Refrigerator + Dishwasher topics.
2. Safety: the agent must NEVER collect payment info, login credentials, or
   personal data, and must NEVER attempt to place orders or check order status
   by scraping. All transactions and order tracking redirect to PartSelect.
"""

import re

from config.settings import settings

# Valid in-scope intents the agent supports.
IN_SCOPE_INTENTS = {
    "search",
    "lookup_part",
    "compatibility",
    "repair_guide",
    "order_placement",   # valid intent -> redirect to PartSelect
    "order_status",      # valid intent -> redirect to PartSelect
}

# Order intents are answered with a redirect, never by scraping/transacting.
REDIRECT_ONLY_INTENTS = {"order_placement", "order_status"}

SUPPORTED_APPLIANCES = ("refrigerator", "fridge", "dishwasher")

# Patterns the agent must never solicit or echo back.
_SENSITIVE_PATTERNS = [
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),          # card-like number
    re.compile(r"\bcvv\b|\bcvc\b", re.IGNORECASE),
    re.compile(r"\bpassword\b|\bpasscode\b", re.IGNORECASE),
    re.compile(r"\bssn\b|social security", re.IGNORECASE),
]


def is_redirect_only(intent: str) -> bool:
    """Order placement/status are handled by redirecting to PartSelect."""
    return intent in REDIRECT_ONLY_INTENTS


def is_in_scope_intent(intent: str) -> bool:
    return intent in IN_SCOPE_INTENTS


def check_input_scope(message: str) -> dict:
    """Best-effort topical scope check for an incoming user message."""
    text = (message or "").lower()
    on_topic = any(word in text for word in SUPPORTED_APPLIANCES)
    return {
        "in_scope": on_topic,
        "reason": "" if on_topic
        else "Out of scope: only Refrigerator and Dishwasher parts are supported.",
    }


def never_request_sensitive_data() -> str:
    """Policy string injected into the agent's system prompt."""
    return (
        "You must never ask for or accept payment details, card numbers, CVV, "
        "login credentials, passwords, or personal data. For any purchase or "
        f"order status request, redirect the user to PartSelect "
        f"({settings.PARTSELECT_BASE_URL}). Never attempt to place an order or "
        "fetch order status yourself."
    )


def sanitize_output(text: str) -> str:
    """Redact anything that looks like sensitive data from an agent reply."""
    cleaned = text or ""
    for pattern in _SENSITIVE_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    return cleaned
