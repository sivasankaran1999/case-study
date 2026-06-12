"""Gemini vision: turn an uploaded photo into a routable text request.

Users can upload an appliance label, a broken part, an error-code screen, or a
wiring photo. We send the image to Gemini (multimodal) and get back a structured
classification plus the key fields (model number, part guess, error code). The
router folds this into the normal text-routing pipeline, so an image becomes
just another signal feeding the EXISTING intents — there is no separate routing
path to maintain, and text-only messages are completely unaffected.
"""

import base64
import binascii
import json
import re

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

genai.configure(api_key=settings.GEMINI_API_KEY.strip())

# Vision uses the fast multimodal model — image understanding is high volume and
# does not need the reasoning model.
_vision_model = genai.GenerativeModel(settings.LLM_FAST_MODEL)

_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB cap to stay well within model limits.
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}

_VISION_PROMPT = (
    "You are the vision assistant for PartSelect, which ONLY helps with "
    "Refrigerator and Dishwasher parts. A user uploaded a photo. Analyze it and "
    "return STRICT JSON with EXACTLY these keys:\n"
    "{\n"
    '  "kind": one of ["model_label","part","error_code","wiring","other"],\n'
    '  "model_number": appliance model number if a rating/spec label is visible, else "",\n'
    '  "brand": brand if visible/identifiable, else "",\n'
    '  "category": one of ["refrigerator","dishwasher",""],\n'
    '  "part_name": if a part is shown, your best guess at its name (e.g. '
    '"defrost thermostat", "door shelf bin", "water inlet valve"), else "",\n'
    '  "error_code": the error/fault code shown on a display, else "",\n'
    '  "description": one short sentence describing what is in the photo,\n'
    '  "suggested_query": the single most likely thing the user wants, phrased '
    "as a short natural request (e.g. \"what does error code E1 mean on my "
    'dishwasher\", \"find this door shelf bin\"), else ""\n'
    "}\n\n"
    "RULES:\n"
    "- kind=model_label when the photo is a rating/spec sticker with a model "
    "number. Read the MODEL number (not the serial number).\n"
    "- kind=part when it shows a physical appliance part.\n"
    "- kind=error_code when a control panel/display shows a fault or error code.\n"
    "- kind=wiring when it shows wiring, a wiring diagram, or electrical "
    "connections.\n"
    "- kind=other for anything that is not a refrigerator/dishwasher part, "
    "label, error screen, or wiring photo.\n"
    "- Only output a model_number you can actually read in the image. Never "
    "guess or invent one.\n"
    "- Return ONLY the JSON object, no prose."
)


def _strip_json(raw: str) -> str:
    if not raw:
        return ""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]
    return raw.strip()


def _parse_image(image: str):
    """Decode a data URL or bare base64 string into (mime_type, bytes).

    Returns ``None`` when the input is unusable (bad base64, too large, or an
    unsupported type) so the caller can fall back to text-only handling.
    """
    if not image or not isinstance(image, str):
        return None

    mime = "image/jpeg"
    data = image.strip()
    m = re.match(r"^data:([^;]+);base64,(.*)$", data, re.DOTALL)
    if m:
        mime = m.group(1).strip().lower()
        data = m.group(2)

    if mime not in _ALLOWED_MIME:
        return None

    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None

    if not raw or len(raw) > _MAX_IMAGE_BYTES:
        return None
    return mime, raw


@retry(wait=wait_exponential(multiplier=1, min=2, max=15), stop=stop_after_attempt(2))
def _generate(prompt: str, mime: str, raw: bytes) -> str:
    resp = _vision_model.generate_content(
        [prompt, {"mime_type": mime, "data": raw}],
        generation_config={
            "temperature": 0.0,
            "response_mime_type": "application/json",
        },
    )
    return getattr(resp, "text", "") or ""


_VALID_KINDS = {"model_label", "part", "error_code", "wiring", "other"}
_VALID_CATEGORIES = {"refrigerator", "dishwasher", ""}


def _normalize(data: dict) -> dict:
    kind = str(data.get("kind", "") or "").strip().lower()
    if kind not in _VALID_KINDS:
        kind = "other"
    category = str(data.get("category", "") or "").strip().lower()
    if category not in _VALID_CATEGORIES:
        category = ""
    return {
        "kind": kind,
        "model_number": str(data.get("model_number", "") or "").strip().upper(),
        "brand": str(data.get("brand", "") or "").strip(),
        "category": category,
        "part_name": str(data.get("part_name", "") or "").strip(),
        "error_code": str(data.get("error_code", "") or "").strip(),
        "description": str(data.get("description", "") or "").strip(),
        "suggested_query": str(data.get("suggested_query", "") or "").strip(),
    }


def analyze_image(image: str, user_text: str = "") -> dict | None:
    """Analyze an uploaded image and return a normalized classification.

    ``image`` is a data URL (``data:image/png;base64,...``) or bare base64.
    Returns ``None`` if the image is unusable or the vision model fails — the
    caller then falls back to text-only behavior.
    """
    parsed = _parse_image(image)
    if parsed is None:
        return None
    mime, raw = parsed

    prompt = _VISION_PROMPT
    if user_text.strip():
        prompt = f"{_VISION_PROMPT}\n\nThe user also wrote: {user_text.strip()}"

    try:
        out = _generate(prompt, mime, raw)
    except Exception:
        return None
    try:
        data = json.loads(_strip_json(out))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return _normalize(data)


def message_from_vision(vision: dict, user_text: str = "") -> str:
    """Build the effective text message the router should classify.

    The image is collapsed into a natural-language request so it flows through
    the EXISTING Flash classifier and intents. The user's own words (if any)
    always take priority; vision fills in what they didn't say.
    """
    text = (user_text or "").strip()
    kind = vision.get("kind", "other")
    model = vision.get("model_number", "")
    part_name = vision.get("part_name", "")
    error_code = vision.get("error_code", "")
    category = vision.get("category", "")
    description = vision.get("description", "")
    suggested = vision.get("suggested_query", "")

    if kind == "model_label":
        if text:
            return f"{text} (my model number is {model})" if model else text
        return (
            f"My appliance model number is {model}."
            if model
            else "I uploaded a photo of my appliance label, but the model "
            "number isn't clear. What should I look for?"
        )

    if kind == "part":
        if text:
            return f"{text} ({description})" if description else text
        if part_name:
            appliance = f"{category} " if category else ""
            return f"I'm looking for this {appliance}part: {part_name}"
        return suggested or "Can you help me identify and find this part?"

    if kind == "error_code":
        appliance = category or "appliance"
        # Fold the detected brand into the text so the slot extractor picks it
        # up — error codes are brand-specific, so this lets the KB lookup answer
        # precisely instead of asking the user which brand they have.
        brand = vision.get("brand", "")
        appliance_phrase = f"{brand} {appliance}".strip() if brand else appliance
        if text:
            return (
                f"{text} (error code {error_code} on my {appliance_phrase})"
                if error_code
                else text
            )
        if error_code:
            return (
                f"My {appliance_phrase} is showing error code {error_code}. "
                "What does it mean and how do I fix it?"
            )
        return suggested or f"My {appliance_phrase} is showing an error code on the display."

    if kind == "wiring":
        if text:
            return f"{text} ({description})" if description else text
        return (
            suggested
            or "I have a wiring question about this photo — can you help me "
            "understand the connections safely?"
        )

    # other / out-of-scope-looking image: defer to user's words or description.
    if text:
        return text
    return suggested or description or "I uploaded a photo — can you help?"
