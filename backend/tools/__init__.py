"""Tool registry for the PartSelect agent.

Maps tool names to callables the executor can dispatch to. Order support is
redirect-only (see get_order_links) — there is no order-scraping tool.
"""

from tools.lookup_part import run as lookup_part
from tools.check_compatibility import run as check_compatibility
from tools.get_repair_guide import run as get_repair_guide
from tools.lookup_error_code import run as lookup_error_code
from tools.search_rag import run as search_rag
from tools.discover_and_index import run as discover_and_index
from tools.get_order_links import (
    get_part_order_link,
    get_order_status_link,
    get_returns_link,
)

TOOL_REGISTRY = {
    "lookup_part": lookup_part,
    "check_compatibility": check_compatibility,
    "get_repair_guide": get_repair_guide,
    "lookup_error_code": lookup_error_code,
    "search_rag": search_rag,
    # Agentic discovery — registered but OFF by default (ENABLE_AGENTIC_DISCOVERY).
    # Plans + scrapes + ranks + indexes new content on demand; never auto-fires
    # in the default live path, so existing latency/behavior is unchanged.
    "discover_and_index": discover_and_index,
    "get_part_order_link": get_part_order_link,
    "get_order_status_link": get_order_status_link,
    "get_returns_link": get_returns_link,
}

__all__ = ["TOOL_REGISTRY"]
