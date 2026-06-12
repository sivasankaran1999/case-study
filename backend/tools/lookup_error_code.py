"""Tool: look up an appliance fault code in the curated, brand-keyed KB.

Codes are brand-specific (e.g. dishwasher "LE" = leak on Samsung but a locked
pump motor on LG), so the KB is grouped by brand and the lookup is brand-aware:

  - Brand known  -> answer from that brand's entry.
  - Brand unknown, one brand has the code -> answer it (noting the brand).
  - Brand unknown, several brands define it differently -> return one grounded
    result that lists each brand's meaning and asks the user to confirm
    brand/model, instead of guessing.

Returns "hit"-shaped dicts (same shape as the repair-guide tool) so the existing
repair synthesizer + RepairGuideCard render the answer unchanged. The KB text is
the grounding context the assistant answers from — no hallucination — and every
answer tells the user to verify against the tech sheet for their exact model.
"""

import json
import os
import re
from functools import lru_cache

_KB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "error_codes.json")

# Error/troubleshooting context words. A purely two-letter alphabetic code
# (e.g. "OE", "LE", "PO") only counts when one of these is present, so we don't
# mistake ordinary words for codes. Codes with a digit or length >= 3 are
# distinctive enough to match on their own.
_CONTEXT_RE = re.compile(
    r"\b(error|fault|code|e-?code|flash\w*|blink\w*|display\w*|shows?|showing|"
    r"says|reading|indicator)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _load_kb() -> dict:
    try:
        with open(os.path.abspath(_KB_PATH), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _norm(code: str) -> str:
    return re.sub(r"[\s\-]", "", code or "").upper()


def canonical_brand(brand: str) -> str:
    """Map a free-text brand (slot value) to a KB brand key, or "" if unknown."""
    if not brand:
        return ""
    aliases = _load_kb().get("brand_aliases", {})
    return aliases.get(brand.strip().lower(), "")


def _code_pattern(norm_code: str) -> re.Pattern:
    """Regex for a normalized code that tolerates spaces/hyphens between chars
    (so "SYEF" matches "SY EF", "F8E4" matches "F8 E4", "8888" matches "88 88")
    and is bounded so it won't match inside a longer token."""
    body = r"[\s\-]*".join(re.escape(ch) for ch in norm_code)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


def _categories_to_search(category: str, kb: dict) -> list[str]:
    cats = [c for c in kb if c not in ("_meta", "brand_aliases")]
    if category in cats:
        return [category]
    return cats


def _find_matches(message: str, category: str, brand: str):
    """Return (matched_code, [(brand, category, entry), ...]) or (None, []).

    Picks the longest code that appears in the message, then collects every
    brand/category entry defining that code (filtered to the user's brand when
    known).
    """
    kb = _load_kb()
    text = message or ""
    has_context = bool(_CONTEXT_RE.search(text))
    want_brand = canonical_brand(brand)

    # (code, brand, category, entry) for every code that matches the message.
    found: list[tuple[str, str, str, dict]] = []
    for cat in _categories_to_search(category, kb):
        for brand_key, codes in (kb.get(cat) or {}).items():
            if want_brand and brand_key != want_brand:
                continue
            for code, entry in codes.items():
                norm = _norm(code)
                distinctive = any(c.isdigit() for c in norm) or len(norm) >= 3
                if not distinctive and not has_context:
                    continue
                if _code_pattern(norm).search(text):
                    found.append((norm, brand_key, cat, entry))

    if not found:
        return None, []

    # Longest matched code wins (so "F8E4" beats "E4", "SY EF" beats "EF").
    best_len = max(len(f[0]) for f in found)
    winners = [f for f in found if len(f[0]) == best_len]
    code = winners[0][0]
    return code, [(b, c, e) for (_, b, c, e) in winners]


def _entry_text(display_code: str, brand: str, category: str, entry: dict) -> str:
    causes = entry.get("causes") or []
    steps = entry.get("steps") or []
    parts = [
        f"{brand} {category} error code {display_code}: {entry.get('title', '')}",
        entry.get("meaning", ""),
    ]
    if causes:
        parts.append("Common causes: " + "; ".join(causes) + ".")
    if steps:
        parts.append(
            "Steps to fix: " + " ".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        )
    parts.append(
        "Note: fault codes vary by brand and model — verify against the tech "
        "sheet inside your appliance or check PartSelect for your exact model."
    )
    return " ".join(p for p in parts if p).strip()


def _display_code(entry: dict, fallback: str) -> str:
    """Pretty code as shown on the appliance (e.g. "OF OF", "Er FF"), parsed
    from the entry title "<display> — <desc>"; falls back to the normalized code."""
    title = entry.get("title", "")
    if "—" in title:
        head = title.split("—", 1)[0].strip()
        # Title may list variants ("5E / 5C"); take the first.
        return head.split("/")[0].strip() or fallback
    return fallback


def _hit(code: str, text: str, category: str, brand: str = "") -> dict:
    symptom = " ".join(p for p in (brand, category, f"error code {code}") if p)
    return {
        "confidence": 0.99,
        "text": text,
        "metadata": {
            "symptom": symptom,
            "text": text,
            "category": category,
            "source": "error-code-kb",
        },
    }


def run(message: str, category: str = "", brand: str = "") -> list[dict]:
    """Look up an error code mentioned in ``message``.

    Returns a single hit-shaped result (grounded answer), or [] if no known
    code is present. When the brand is unknown and the code is brand-ambiguous,
    the single result enumerates each brand's meaning and asks for the brand.
    """
    code, matches = _find_matches(message, category, brand)
    if not code or not matches:
        return []

    if len(matches) == 1:
        b, cat, entry = matches[0]
        disp = _display_code(entry, code)
        return [_hit(disp, _entry_text(disp, b, cat, entry), cat, b)]

    # Brand-ambiguous: present every interpretation and ask the user to confirm.
    cat = matches[0][1]
    disp = _display_code(matches[0][2], code)
    lines = [f"Error code {disp} means different things depending on the brand:"]
    for b, c, entry in matches:
        lines.append(f"- On {b} ({c}): {entry.get('title', '')} — {entry.get('meaning', '')}")
    lines.append(
        "Tell me your appliance brand or model number and I'll give you the exact "
        "causes and fix steps."
    )
    return [_hit(disp, " ".join(lines), cat)]
