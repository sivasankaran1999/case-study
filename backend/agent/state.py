"""Shared LangGraph state for the PartSelect agent.

Shared state for the LangGraph agent (router -> executor -> synthesizer).
"""

from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # Conversation
    message: str
    conversation_history: List[Dict[str, str]]
    model_number: Optional[str]
    # Optional uploaded image (data URL / base64). When present the router runs
    # vision analysis first and folds the result into the routed message/slots.
    image: Optional[str]

    # Routing / control
    intent: Optional[str]
    part_number: Optional[str]
    category: Optional[str]  # refrigerator | dishwasher
    iterations: int
    # One targeted question to ask when the classifier isn't confident enough
    # to act (set by the router, surfaced by the synthesizer).
    clarify_question: Optional[str]
    # Flash-extracted, filler-free search terms for this turn (used by the
    # executor when building Pinecone queries). Empty -> fall back to the
    # executor's existing query-building logic.
    clean_search_query: Optional[str]

    # Persistent conversation memory (layer 3 of the hybrid router). Carries
    # everything the user has already told us so no node ever asks twice:
    #   model_number, brand, category, last_part_number, last_part_name,
    #   last_symptom. Slots are NEVER overwritten with empty values, so a model
    #   given in turn 1 is still here in turn 10. Available to every node.
    slots: Dict[str, Any]

    # Tool results accumulated during execution
    tool_results: List[Dict[str, Any]]
    parts: List[Dict[str, Any]]
    repair_steps: List[Dict[str, Any]]
    repair_meta: Optional[Dict[str, Any]]
    order_url: Optional[str]  # PartSelect redirect for order placement / status
    # Disambiguation choices for a vague query (part_number, name, price)
    options: List[Dict[str, Any]]

    # Final response surfaced to the API
    # text | part | repair_guide | clarify | intent_clarify
    # | order_redirect | order_status_redirect | out_of_scope
    # (a targeted clarification question is surfaced as a plain `text` reply)
    response_type: str
    response_message: str
    confidence: float
