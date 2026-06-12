"""LangGraph assembly for the PartSelect agent."""

from langgraph.graph import END, StateGraph
from langchain_core.tracers.context import collect_runs

from agent.state import AgentState
from agent.nodes.router import router_node
from agent.nodes.executor import executor_node
from agent.nodes.synthesizer import synthesizer_node
from observability import get_request_id


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("synthesizer", synthesizer_node)

    workflow.set_entry_point("router")
    workflow.add_edge("router", "executor")
    workflow.add_edge("executor", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile()


agent_graph = build_graph()


def run_agent(
    message: str,
    model_number: str | None = None,
    conversation_history: list | None = None,
    image: str | None = None,
) -> dict:
    """Invoke the agent graph and return the final state."""
    initial: AgentState = {
        "message": message,
        "model_number": model_number,
        "conversation_history": conversation_history or [],
        "image": image,
        "iterations": 0,
        "tool_results": [],
        "parts": [],
        "repair_steps": [],
        "confidence": 0.0,
        "slots": {},
        "clarify_question": "",
        "clean_search_query": "",
    }
    # Tag the LangSmith run so traces are searchable by request id and carry the
    # turn's context (no-op when tracing is disabled).
    config = {
        "run_name": "partselect_agent",
        "tags": ["partselect", "agent"],
        "metadata": {
            "request_id": get_request_id(),
            "has_image": bool(image),
            "has_model": bool(model_number),
            "history_turns": len(conversation_history or []),
        },
    }
    # Capture the root LangSmith run id so the frontend can attach 👍/👎 feedback
    # to this exact trace. When tracing is disabled, no runs are collected and
    # trace_id stays None — feedback then logs locally only (graceful degrade).
    with collect_runs() as cb:
        result = agent_graph.invoke(initial, config=config)
    try:
        result["trace_id"] = str(cb.traced_runs[0].id) if cb.traced_runs else None
    except Exception:
        result["trace_id"] = None
    return result
