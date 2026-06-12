"""Synthesizer node: turns tool results into the API response shape."""

import json
import re

from agent.state import AgentState
from agent.utils import (
    build_intent_options,
    build_part_options,
    is_model_statement,
    is_problem_followup,
    parse_json_field,
    topic_from_message,
)
from guardrails.nemo_gateway import sanitize_output
from rag.llm import synthesize_answer


def _context_from_tool_results(tool_results: list[dict], parts: list[dict]) -> str:
    """Assemble retrieved text for the reasoning model."""
    chunks = []
    for tr in tool_results:
        result = tr.get("result")
        if isinstance(result, list):
            for hit in result[:3]:
                if isinstance(hit, dict):
                    text = hit.get("text") or hit.get("metadata", {}).get("text", "")
                    if text:
                        chunks.append(text[:1500])
        elif isinstance(result, dict):
            text = result.get("text") or result.get("description", "")
            if text:
                chunks.append(text[:1500])
    for p in parts[:3]:
        bits = [
            p.get("name", ""),
            f"Part #{p.get('part_number', '')}",
            p.get("description", ""),
        ]
        steps = p.get("installation_steps") or []
        if steps:
            bits.append("Installation: " + " ".join(steps[:8]))
        chunks.append(" ".join(b for b in bits if b))
    return "\n\n".join(c for c in chunks if c.strip())


# Lines that are navigation / boilerplate / index-prefix, not real repair steps.
_JUNK_PATTERNS = re.compile(
    r"base64|image-removed|view the faqs|model number|for example\)|"
    r"https?://|\]\(|model tag|paper sticker|metal plate|need more info|"
    r"easyapplianceparts|partselect\.com|sign in|log in|^\W*$|"
    r"^repair guide:|^appliance:|^symptoms:|shop with confidence|"
    r"genuine parts|back to top|^category:",
    re.IGNORECASE,
)


def _is_junk_step(text: str) -> bool:
    if len(text) < 15:
        return True
    if _JUNK_PATTERNS.search(text):
        return True
    # Mostly non-alphabetic (links, symbols) -> junk.
    letters = sum(c.isalpha() for c in text)
    if letters < len(text) * 0.5:
        return True
    return False


# A list item: a bullet (-, *, •) or a number (1. / 1)) at the start of a line.
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)")


def _clean_instruction(text: str) -> str:
    # Strip markdown links/images and stray markup.
    text = re.sub(r"!?\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"[*_`#>]+", "", text)
    # Strip any leading bullet/number marker left over from sentence splitting
    # (e.g. "- Inspection: ..." -> "Inspection: ...").
    text = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _split_repair_message(text: str) -> tuple[str, list[dict]]:
    """Split a synthesized repair answer into ``(lead_in, ordered_steps)``.

    The lead-in is the framing prose *before* the first list item — it becomes
    the chat bubble. The list items become the card's steps. This is what stops
    the answer text and the step card from duplicating each other (and stops the
    intro sentence from being mislabeled "Step 1").

    Handles both bullet (``-`` / ``*`` / ``•``) and numbered lists, folds
    continuation lines into the preceding step, and falls back to sentence
    segmentation (first sentence = lead-in) when there are no list markers.
    """
    lead_parts: list[str] = []
    raw_steps: list[str] = []
    seen_list = False

    for line in (text or "").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        m = _LIST_ITEM_RE.match(stripped)
        if m:
            seen_list = True
            raw_steps.append(_clean_instruction(m.group(1)))
        elif seen_list and raw_steps:
            # Wrapped continuation of the previous list item.
            raw_steps[-1] = f"{raw_steps[-1]} {_clean_instruction(stripped)}".strip()
        elif not seen_list:
            lead_parts.append(stripped)

    lead = _clean_instruction(" ".join(lead_parts))

    # No list markers — segment into sentences and treat the first as the lead.
    if not raw_steps and text:
        sentences = [
            _clean_instruction(s)
            for s in re.split(r"(?<=[.!?])\s+", text[:3000])
        ]
        sentences = [s for s in sentences if s]
        if sentences:
            lead = lead or sentences[0]
            raw_steps = sentences[1:]

    steps: list[dict] = []
    for c in raw_steps:
        if _is_junk_step(c):
            continue
        steps.append({"step_number": len(steps) + 1, "instruction": c})
        if len(steps) >= 8:
            break
    return lead, steps


def _repair_steps_from_text(text: str) -> list[dict]:
    """Back-compat shim — steps only (callers that don't need the lead-in)."""
    return _split_repair_message(text)[1]


def _build_repair_from_hits(hits: list[dict]) -> tuple[str, list[dict], dict | None]:
    if not hits:
        return (
            "I couldn't find a repair guide for that issue. Try describing the "
            "symptom (e.g. leaking, not making ice, won't start).",
            [],
            None,
        )

    top = hits[0]
    meta = top.get("metadata", {})
    text = top.get("text") or meta.get("text", "")
    symptom = meta.get("symptom") or "repair issue"
    title = symptom.replace("-", " ").title()

    steps = _repair_steps_from_text(text)
    repair_meta = {
        "title": f"How to fix: {title}",
        "time_estimate": None,
        "difficulty": None,
    }
    message = (
        f"I found a repair guide for {title}. "
        "Here are the recommended troubleshooting steps:"
    )
    return message, steps, repair_meta


# Phrases that mean "I don't actually have an answer." When synthesis falls
# back to one of these (thin/irrelevant retrieval), we must NOT dress it up as a
# repair guide with fabricated steps and a mismatched title — show a clean,
# honest fallback instead.
_LOW_VALUE_RE = re.compile(
    r"does(?:n'?t| not)\s+contain|do not\s+contain|provided context|"
    r"could ?n'?t\s+find|could not\s+find|no (?:specific )?(?:repair )?guid|"
    r"no specific (?:repair|information|guidance)|insufficient|"
    r"don'?t have (?:enough|a specific|specific)|"
    r"do not have (?:enough|a specific|specific)|"
    r"not enough (?:information|context|detail)|"
    r"no (?:information|details?) (?:about|on|for)",
    re.IGNORECASE,
)


def _is_low_value_answer(text: str) -> bool:
    """True when a synthesized answer is really a 'no information' disclaimer."""
    return bool(_LOW_VALUE_RE.search(text or ""))


def _repair_fallback(state: AgentState, parts: list[dict]) -> str:
    """Honest, helpful message when we have no real repair guide for the issue —
    no fabricated steps, no mismatched guide title."""
    slots = state.get("slots") or {}
    symptom = (slots.get("last_symptom") or "").strip()
    model = (state.get("model_number") or "").strip()
    sym = f' for "{symptom}"' if symptom else ""

    if parts:
        return (
            f"I don't have a step-by-step guide{sym} yet, but these parts are "
            "commonly involved in this kind of repair — verify the fit for your "
            "model before ordering."
        )
    if model:
        return (
            f"I don't have a specific repair guide{sym} for {model} yet. This can "
            "be a more involved repair — I'd recommend the repair guides on "
            "PartSelect, or tell me the exact symptom and I'll point you to the "
            "likely part."
        )
    return (
        f"I don't have a specific repair guide{sym} yet. Tell me your model "
        "number and the exact symptom (e.g. \"not cooling\", \"leaking\", "
        "\"won't drain\"), and I'll point you to the likely part and a guide."
    )


def _focused_followup_answer(message: str, part: dict) -> str:
    """For targeted follow-ups ('is it in stock?', 'how much?', 'install?'),
    return a short direct sentence. Empty string -> card-only (no text)."""
    text = (message or "").lower()
    name = part.get("name") or "this part"
    pn = part.get("part_number", "")
    price = part.get("price")
    in_stock = part.get("in_stock")
    steps = part.get("installation_steps") or []

    # Stock / availability
    if re.search(r"in\s+stock|available|availability", text):
        if in_stock is True:
            return f"Yes — {name} ({pn}) is in stock and ships within one business day."
        if in_stock is False:
            return f"{name} ({pn}) is currently out of stock on PartSelect."

    # Price / cost
    if re.search(r"how\s+much|price|cost|expensive", text):
        if price not in (None, ""):
            return f"{name} ({pn}) costs ${float(price):.2f}."

    # Installation
    if re.search(r"install|replace|how\s+do\s+i\s+put|fit\s+it\s+in", text):
        if steps:
            joined = " ".join(f"{i}. {s}" for i, s in enumerate(steps[:6], 1))
            return f"Installing {name} ({pn}): {joined}"
        return (
            f"{name} ({pn}) installs easily — see the step-by-step guide and "
            "video on its PartSelect product page."
        )
    return ""


def _first_sentence(text: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""
    first = re.split(r"(?<=[.!?])\s+", text)[0].strip()
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0] + "…"
    return first


def _part_fits_model(part: dict, model_number: str) -> bool | None:
    """True/False if we can tell from the part's compatibility list, else None."""
    compat = part.get("compatible_with") or []
    if not model_number or not compat:
        return None
    mn = model_number.upper()
    return any(str(m).upper() == mn for m in compat)


def _why_recommended(part: dict, slots: dict, model_number: str) -> str:
    """Explain WHY this part is the answer, grounded only in real part/slot
    fields — what it is, the symptom it matches, and model compatibility — so
    we never reply with a bare "buy part #X". Returns "" if there's nothing
    concrete to say (the card then stands on its own)."""
    name = (part.get("name") or "This part").strip()
    pn = part.get("part_number", "")
    desc = _first_sentence(part.get("description", ""))
    fixes = [s for s in (part.get("fixes_symptoms") or []) if s][:2]
    symptom = (slots or {}).get("last_symptom") or ""

    sentences = []

    # 1. What it is / what it commonly does.
    lead = name if not pn else f"{name} ({pn})"
    if desc:
        sentences.append(f"{lead} — {desc[0].lower() + desc[1:]}" if desc[0].isupper() else f"{lead} — {desc}")
    else:
        sentences.append(f"Here's {lead}.")

    # 2. Symptom match — tie the recommendation to what fails / what they said.
    if fixes:
        fix_text = " and ".join(fixes)
        if symptom:
            sentences.append(
                f"It's commonly replaced to fix {fix_text}, which matches the "
                f"symptom you described (\"{symptom}\")."
            )
        else:
            sentences.append(f"It's commonly replaced to fix {fix_text}.")
    elif symptom:
        sentences.append(f"It's a common fix for \"{symptom}\".")

    # 3. Compatibility with the user's model.
    fits = _part_fits_model(part, model_number)
    if fits is True:
        sentences.append(f"It's confirmed compatible with your model {model_number}.")
    elif fits is False:
        sentences.append(
            f"Note: it isn't on the parts list for {model_number}, so verify the "
            "fit on PartSelect before ordering."
        )
    elif model_number:
        sentences.append(
            f"Double-check it against your model {model_number} on the product page."
        )
    else:
        sentences.append(
            "Share your model number and I'll confirm it's the right fit."
        )

    return " ".join(sentences).strip()


def _display_search_query(state: AgentState) -> str:
    """Human-readable label for what we searched — not the raw user message.

    After the model-number gate, the user's reply is often just a model number
    (e.g. GFSS2HCYCSS) while ``clean_search_query`` still holds the part they
    asked for (e.g. icemaker). Prefer that over echoing the model back.
    """
    clean = (state.get("clean_search_query") or "").strip()
    if clean:
        return clean
    slots = state.get("slots") or {}
    part_name = (slots.get("last_part_name") or "").strip()
    if part_name:
        return part_name
    message = (state.get("message") or "").strip()
    if message and not is_model_statement(message):
        return message
    return ""


def _clarify_response(parts: list[dict], query: str = "", model_number: str = "") -> dict:
    """Ask the user to pick from several matching parts instead of dumping
    multiple full cards for a vague query."""
    options = build_part_options(parts)
    label = query.strip()
    if label and model_number:
        intro = (
            f"For your **{label}** on model **{model_number}**, "
            "I found a few options."
        )
    elif label:
        intro = f'I found a few parts that match "{label}".'
    else:
        intro = "I found a few parts that match your search."
    # If we know the model, point out which options actually fit it.
    has_fit_info = any(o.get("fits_model") is not None for o in options)
    if model_number and has_fit_info:
        n_fit = sum(1 for o in options if o.get("fits_model") is True)
        if n_fit:
            tail = (
                " The ones marked compatible fit your model. "
                "Which would you like details on?"
            )
        else:
            tail = (
                " I couldn't confirm which fit your model from our parts list — "
                "use **Verify fit on PartSelect** on any card. "
                "Which would you like details on?"
            )
    else:
        tail = " Which one would you like more details on?"

    return {
        "response_type": "clarify",
        "response_message": sanitize_output(f"{intro}{tail}"),
        "options": options,
        "confidence": 0.5,
    }


def _llm_message(state: AgentState, parts: list[dict], fallback: str) -> str:
    """Try strong-model synthesis; fall back to the deterministic template."""
    intent = state.get("intent", "search")
    message = state.get("message", "")
    tool_results = state.get("tool_results") or []
    context = _context_from_tool_results(tool_results, parts)
    answer = synthesize_answer(message, intent, context)
    return answer or fallback


def synthesizer_node(state: AgentState) -> dict:
    intent = state.get("intent", "search")
    tool_results = state.get("tool_results") or []
    parts = state.get("parts") or []
    confidence = float(state.get("confidence") or 0.0)
    order_url = state.get("order_url")
    part_number = state.get("part_number") or ""
    model_number = state.get("model_number") or ""

    if intent == "out_of_scope":
        return {
            "response_type": "out_of_scope",
            "response_message": sanitize_output(
                "I can only help with Refrigerator and Dishwasher parts — finding "
                "parts, troubleshooting, compatibility, and ordering. "
                "Can I help you with one of those?"
            ),
            "confidence": 1.0,
        }

    if intent == "greeting":
        return {
            "response_type": "text",
            "response_message": (
                "Hi! I'm the PartSelect assistant for Refrigerator and Dishwasher "
                "parts.\n\n**What can I help you with today?**\n\n"
                "• Find a replacement part\n"
                "• Diagnose an appliance issue\n"
                "• Repair instructions\n"
                "• Check part compatibility"
            ),
            "confidence": 1.0,
        }

    if intent == "sensitive":
        return {
            "response_type": "text",
            "response_message": (
                "For your security, never share payment details, card numbers, or "
                "passwords here. All purchases and account info are handled safely "
                "on PartSelect's checkout. I can help you find the right part, "
                "check compatibility, or troubleshoot — what do you need?"
            ),
            "confidence": 1.0,
        }

    if intent == "clarify":
        # One targeted question from the classifier, surfaced as a plain reply.
        question = (
            state.get("clarify_question")
            or "Could you give me a little more detail so I can point you to the "
            "right part or guide?"
        )
        return {
            "response_type": "text",
            "response_message": sanitize_output(question),
            "model_number": model_number or None,
            "confidence": 0.5,
        }

    if intent == "intent_clarify":
        topic = topic_from_message(state.get("message", ""))
        options = build_intent_options(topic, model_number)
        label = topic or "that"
        return {
            "response_type": "intent_clarify",
            "response_message": sanitize_output(
                f"I can help with **{label}**. What would you like to do?"
            ),
            "options": options,
            "confidence": 0.5,
        }

    if intent == "provide_model":
        model = state.get("model_number") or ""
        msg = (
            f"Got it — I've noted your model **{model}**. "
            if model
            else "Thanks! "
        ) + (
            "What can I help you with? You can ask if a specific part fits, "
            "search for a part, or describe a problem you're having."
        )
        return {
            "response_type": "text",
            "response_message": sanitize_output(msg),
            "model_number": model,
            "confidence": 1.0,
        }

    if intent == "order_status":
        result = tool_results[0]["result"] if tool_results else {}
        return {
            "response_type": "order_status_redirect",
            "response_message": sanitize_output(result.get("message", "")),
            "order_url": result.get("url") or order_url,
            "confidence": 1.0,
        }

    if intent == "returns":
        result = tool_results[0]["result"] if tool_results else {}
        return {
            "response_type": "returns_redirect",
            "response_message": sanitize_output(result.get("message", "")),
            "order_url": result.get("url") or order_url,
            "confidence": 1.0,
        }

    if intent == "order_placement":
        result = tool_results[0]["result"] if tool_results else {}
        return {
            "response_type": "order_redirect",
            "response_message": sanitize_output(result.get("message", "")),
            "order_url": result.get("url") or order_url,
            "parts": parts,
            "confidence": 1.0,
        }

    if intent == "compatibility":
        result = tool_results[0]["result"] if tool_results else {}
        if result.get("error"):
            # missing_entities (no part) -> plain prompt; missing_model -> prompt
            # plus the part card so the user sees what they're matching.
            return {
                "response_type": "part" if parts else "text",
                "response_message": sanitize_output(result.get("message", "")),
                "parts": parts,
                "confidence": 0.0,
            }
        compatible = result.get("compatible", False)
        pn = result.get("part_number", part_number)
        model = result.get("model_number", model_number)
        if compatible:
            msg = (
                f"Yes — {pn} is listed as compatible with model {model} "
                "on PartSelect."
            )
        else:
            msg = (
                f"{pn} does not appear on the official parts list for "
                f"{model}. I'd recommend verifying on PartSelect before ordering."
            )
        return {
            "response_type": "part" if parts else "text",
            "response_message": sanitize_output(msg),
            "parts": parts,
            "confidence": confidence,
        }

    if intent == "install_help":
        if parts:
            return {
                "response_type": "part",
                "response_message": sanitize_output(
                    _focused_followup_answer(state.get("message", ""), parts[0])
                ),
                "parts": parts,
                "confidence": confidence,
            }
        return {
            "response_type": "text",
            "response_message": sanitize_output(
                f"I couldn't find installation details for {part_number or 'that part'}. "
                "Try providing the exact PS part number."
            ),
            "confidence": 0.0,
        }

    if intent == "lookup_part":
        # Exact PS lookup -> single card. Vague (no part #) with several
        # matches -> ask which one.
        if not part_number and len(parts) > 1:
            return _clarify_response(
                parts, _display_search_query(state), state.get("model_number") or ""
            )
        if parts:
            # A targeted follow-up ("is it in stock?", "how much?") gets a short
            # direct answer; otherwise explain WHY this part is the recommendation
            # instead of showing a bare card.
            followup = _focused_followup_answer(state.get("message", ""), parts[0])
            why = followup or _why_recommended(
                parts[0], state.get("slots") or {}, model_number
            )
            return {
                "response_type": "part",
                "response_message": sanitize_output(why),
                "parts": parts[:1] if part_number else parts,
                "confidence": confidence,
            }
        return {
            "response_type": "text",
            "response_message": sanitize_output(
                "I couldn't find that part. Double-check the PS number or describe "
                "what you need."
            ),
            "confidence": 0.0,
        }

    if intent == "repair_guide":
        hits = []
        for tr in tool_results:
            if tr.get("tool") == "get_repair_guide":
                hits = tr.get("result") or []
                break
        message, steps, repair_meta = _build_repair_from_hits(hits)
        final_message = _llm_message(state, parts, message)
        # Split the synthesized answer into a framing lead-in + steps. Prefer the
        # synthesized steps; fall back to raw-chunk steps only if synthesis
        # didn't produce a usable list.
        lead, llm_steps = _split_repair_message(final_message)
        usable_steps = (
            llm_steps if len(llm_steps) >= 2
            else (steps if len(steps) >= 2 else [])
        )
        low_value = _is_low_value_answer(final_message)

        # Only render the structured "How to fix" card when we actually have a
        # relevant guide WITH usable steps. Otherwise give a clean fallback (plus
        # any recommended parts) — never turn a non-answer into fake steps or
        # show a guide title that doesn't match the question.
        if low_value or not usable_steps:
            msg = _repair_fallback(state, parts) if low_value else final_message
            return {
                "response_type": "part" if parts else "text",
                "response_message": sanitize_output(msg),
                "parts": parts,
                "confidence": 0.0 if low_value else confidence,
            }

        # The bubble carries ONLY the lead-in so it doesn't restate the steps
        # shown in the card. Fall back to a clean framing line if synthesis gave
        # us steps with no intro.
        title = (repair_meta or {}).get("title", "").replace("How to fix: ", "")
        bubble = lead or (
            f"Here's how to troubleshoot {title.lower()}."
            if title
            else "Here are the steps to troubleshoot this issue."
        )
        return {
            "response_type": "repair_guide",
            "response_message": sanitize_output(bubble),
            "repair_steps": usable_steps,
            "repair_meta": repair_meta,
            "parts": parts,
            "confidence": confidence,
        }

    # search — prefer parts, fall back to repair guide content
    repair_hits = []
    for tr in tool_results:
        if tr.get("tool") == "get_repair_guide":
            repair_hits = tr.get("result") or []

    # Multiple matches for a vague search -> disambiguate instead of dumping
    # several full cards.
    if len(parts) > 1:
        return _clarify_response(
            parts, _display_search_query(state), state.get("model_number") or ""
        )

    if parts:
        # Symptom-driven discovery: explain WHY this part matches (what it does,
        # the symptom, model fit) rather than dropping a card with no rationale.
        return {
            "response_type": "part",
            "response_message": sanitize_output(
                _why_recommended(parts[0], state.get("slots") or {}, model_number)
            ),
            "parts": parts,
            "confidence": confidence,
        }

    if repair_hits:
        message, steps, repair_meta = _build_repair_from_hits(repair_hits)
        return {
            "response_type": "repair_guide",
            "response_message": sanitize_output(message),
            "repair_steps": steps,
            "repair_meta": repair_meta,
            "parts": parts,
            "confidence": confidence,
        }

    return {
        "response_type": "text",
        "response_message": sanitize_output(
            "I couldn't find a strong match. Try a part number (PS…), your model "
            "number, or describe the symptom (e.g. dishwasher leaking)."
        ),
        "confidence": 0.0,
    }
