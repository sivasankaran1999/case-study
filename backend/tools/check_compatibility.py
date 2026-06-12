"""Tool: check whether a part is compatible with a given model number."""

from rag.self_heal import check_compatibility


def run(part_number: str, model_number: str, category: str = "") -> dict:
    return check_compatibility(part_number, model_number, category=category)
