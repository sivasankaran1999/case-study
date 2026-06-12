"""Router node: the hybrid, three-layer intent router.

Layer 1 — deterministic rules for 100%-unambiguous messages (a bare PS number,
an order-tracking request, a greeting, an out-of-scope appliance, a model
statement, or sensitive data). Anything ambiguous is deferred.

Layer 2 — Gemini Flash classifies everything the rules didn't catch, returning
the intent, confidence, extracted entities, the action the user wants, and
whether one clarifying question is needed.

Layer 3 — slot memory persists everything the user has told us across the whole
conversation (model number, brand, category, last part, last symptom) so no
node ever asks twice. Slots are written into the state for every node to use.
"""

from agent.classifier import INTENT_MAP, classify as flash_classify
from agent.slots import build_slots
from rag.vision import analyze_image, message_from_vision
from agent.state import AgentState
from agent.utils import (
    ORDER_CART_RE,
    extract_part_number,
    infer_category,
    is_followup_reference,
    is_model_statement,
    model_prompt_for,
    pending_compat_part,
    pending_model_part,
    unambiguous_intent,
)

# Shown when Flash classification is unavailable or fails. We never silently
# fall back to keyword/regex routing — we ask the user to rephrase instead.
_CLASSIFY_UNAVAILABLE_MESSAGE = "I didn't quite understand that, could you rephrase?"


def _result(
    state: AgentState,
    *,
    intent: str,
    part_number: str | None,
    model_number: str | None,
    category: str,
    slots: dict,
    clarify_question: str = "",
    clean_search_query: str = "",
    message: str | None = None,
) -> dict:
    out = {
        "intent": intent,
        "part_number": part_number,
        "model_number": model_number,
        "category": category or "",
        "slots": slots,
        "clarify_question": clarify_question,
        "clean_search_query": clean_search_query,
        "iterations": state.get("iterations", 0) + 1,
        "tool_results": [],
        "parts": [],
        "repair_steps": [],
        "repair_meta": None,
        "order_url": None,
    }
    # Persist the effective message so downstream nodes (executor's repair /
    # search queries) use the vision-rewritten text, not the original input.
    if message is not None:
        out["message"] = message
    return out


def router_node(state: AgentState) -> dict:
    message = state.get("message", "") or ""
    saved_model = state.get("model_number")
    history = state.get("conversation_history") or []

    # ---- Image upload: run vision first, then route normally. ----
    # An uploaded photo (appliance label, broken part, error screen, wiring) is
    # collapsed into a natural-language request that flows through the SAME
    # classifier and intents below — no separate routing path. A readable model
    # number is promoted to the saved model so every later turn is personalized.
    image = state.get("image")
    if image:
        vision = analyze_image(image, message)
        if vision:
            message = message_from_vision(vision, message)
            if vision.get("model_number"):
                saved_model = vision["model_number"]
        elif not message:
            # Unreadable image and nothing typed — ask for a bit of context.
            base_slots = build_slots(message, history, saved_model, None)
            return _result(
                state,
                intent="clarify",
                part_number=None,
                model_number=(base_slots.get("model_number") or "").upper() or None,
                category=base_slots.get("category") or "",
                slots=base_slots,
                clarify_question=(
                    "I couldn't quite read that image. Could you tell me what "
                    "you'd like help with — finding a part, an error code, or a "
                    "repair?"
                ),
            )

    explicit_part = extract_part_number(message)

    # ---- Resume a pending compatibility check. ----
    # If the previous turn asked for a model to verify a specific part and the
    # user replied with just that model, run the compatibility check now instead
    # of letting the bare-model rule below acknowledge it and drop the request.
    if not explicit_part and is_model_statement(message):
        pending_part = pending_compat_part(history)
        if pending_part:
            slots = build_slots(message, history, saved_model, None)
            return _result(
                state,
                intent="compatibility",
                part_number=pending_part,
                model_number=(slots.get("model_number") or "").upper() or None,
                category=slots.get("category") or infer_category(message),
                slots=slots,
                message=message,
            )

        # ---- Resume a pending model-number request (part-find gate). ----
        # If the previous turn asked for the model to find a named part and the
        # user replied with just that model, run the search now using the
        # remembered part — instead of acknowledging the model and dropping it.
        pending_search = pending_model_part(history)
        if pending_search:
            slots = build_slots(message, history, saved_model, None)
            return _result(
                state,
                intent="search",
                part_number=None,
                model_number=(slots.get("model_number") or "").upper() or None,
                category=(
                    slots.get("category")
                    or infer_category(pending_search)
                    or infer_category(message)
                ),
                slots=slots,
                clean_search_query=pending_search,
                message=message,
            )

    # ---- Layer 1: deterministic rules for 100%-unambiguous messages. ----
    rule_intent = unambiguous_intent(message, explicit_part)
    if rule_intent is not None:
        slots = build_slots(message, history, saved_model, None)
        return _result(
            state,
            intent=rule_intent,
            part_number=explicit_part,
            model_number=(slots.get("model_number") or "").upper() or None,
            category=slots.get("category") or infer_category(message),
            slots=slots,
            message=message,
        )

    # ---- Layer 2: Gemini Flash for everything ambiguous. ----
    base_slots = build_slots(message, history, saved_model, None)
    flash = flash_classify(message, history, base_slots)

    # No silent regex fallback. If Flash is unavailable or fails, ask the user
    # to rephrase rather than guessing with brittle keyword rules.
    if flash is None:
        return _result(
            state,
            intent="clarify",
            part_number=explicit_part,
            model_number=(base_slots.get("model_number") or "").upper() or None,
            category=base_slots.get("category") or infer_category(message),
            slots=base_slots,
            clarify_question=_CLASSIFY_UNAVAILABLE_MESSAGE,
            message=message,
        )

    entities = flash.get("entities", {})
    inferred_category = flash.get("inferred_category")
    # ---- Layer 3: rebuild slots with this turn's extracted entities. The
    # inferred category (from a model number) fills the category slot only when
    # nothing else set it. ----
    slots = build_slots(message, history, saved_model, entities, inferred_category)

    intent = INTENT_MAP.get(flash.get("intent", ""), "search")

    # Resolve effective entities. Slots already merge + persist everything the
    # user has told us, so the saved model number flows into every tool call
    # automatically without re-asking.
    model_number = (slots.get("model_number") or "").upper() or None
    category = entities.get("category") or slots.get("category") or infer_category(message)
    part_number = explicit_part or (entities.get("part_number") or "").upper() or None
    # A contextual follow-up ("is it in stock?", "install this") inherits the
    # last part discussed; a brand-new search does not.
    if not part_number and is_followup_reference(message):
        part_number = slots.get("last_part_number")

    # ---- Critical rule: "purchase"/"buy" = find & buy a part, NOT checkout. ----
    # Only an explicit cart/checkout action on a known part is order placement.
    if intent == "order_placement" and not ORDER_CART_RE.search(message):
        intent = "lookup_part" if part_number else "search"

    # ---- Clarification: ask ONE targeted question instead of guessing. ----
    clarify_question = ""
    if flash.get("needs_clarification") and flash.get("clarification_question"):
        intent = "clarify"
        clarify_question = flash["clarification_question"]

    # ---- Model-number gate: collect the model BEFORE recommending a part. ----
    # Finding/buying a specific named part (e.g. an ice maker) is model-specific,
    # so recommending options before we know the unit can surface parts that
    # don't fit. We ask for the model once when: the user wants to find/buy a
    # NAMED part, gave no PS number, has no saved model, and we haven't already
    # asked (pending_model_part). A bare-model reply next turn resumes the search
    # above; any other reply falls through and shows options (we never re-ask).
    part_name = (entities.get("part_name") or "").strip()
    if (
        intent in ("lookup_part", "search")
        and flash.get("action") in ("buy", "find")
        and part_name
        and not part_number
        and not model_number
        and pending_model_part(history) is None
    ):
        return _result(
            state,
            intent="clarify",
            part_number=None,
            model_number=None,
            category=category,
            slots=slots,
            clarify_question=model_prompt_for(part_name),
            message=message,
        )

    return _result(
        state,
        intent=intent,
        part_number=part_number,
        model_number=model_number,
        category=category,
        slots=slots,
        clarify_question=clarify_question,
        clean_search_query=flash.get("clean_search_query") or "",
        message=message,
    )
