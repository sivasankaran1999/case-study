"""Curated evaluation dataset for the PartSelect RAG pipeline.

Each case is a representative Refrigerator/Dishwasher query paired with a
short, factual reference answer. Cases are split by retrieval namespace:

- ``repair-guides``  -> symptom/troubleshooting queries
- ``parts``          -> part-name lookup queries

The reference answers are intentionally concise and grounded in what
PartSelect's public guides/product pages convey; RAGAS uses them for
context-precision/recall (reference-aware) while faithfulness and answer
relevancy score the generated answer against the retrieved context.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    question: str
    reference: str
    namespace: str  # "repair-guides" | "parts"
    category: str   # "refrigerator" | "dishwasher"
    intent: str     # passed to synthesize_answer (repair_guide | search)


# --- Refrigerator: troubleshooting / repair ------------------------------- #
REFRIGERATOR_REPAIR = [
    EvalCase(
        question="My refrigerator is not cooling",
        reference=(
            "A refrigerator that isn't cooling is commonly caused by a failed "
            "evaporator fan motor, dirty condenser coils, a faulty start relay, "
            "or a defective temperature/cold control thermostat. Check that the "
            "condenser coils are clean and the evaporator fan runs; replace the "
            "failed component if found."
        ),
        namespace="repair-guides",
        category="refrigerator",
        intent="repair_guide",
    ),
    EvalCase(
        question="My ice maker stopped making ice",
        reference=(
            "An ice maker that stops producing ice is usually due to a frozen or "
            "clogged water line, a failed water inlet valve, or a defective ice "
            "maker assembly. Verify water supply and the inlet valve, then "
            "replace the ice maker module if it doesn't cycle."
        ),
        namespace="repair-guides",
        category="refrigerator",
        intent="repair_guide",
    ),
    EvalCase(
        question="There is frost building up in my freezer",
        reference=(
            "Frost buildup in a freezer typically points to a defrost system "
            "failure — a defective defrost heater, defrost thermostat, or defrost "
            "timer/control — or a bad door gasket letting humid air in. Test the "
            "defrost components and replace the faulty part."
        ),
        namespace="repair-guides",
        category="refrigerator",
        intent="repair_guide",
    ),
    EvalCase(
        question="Water dispenser not working on my fridge",
        reference=(
            "A non-working water dispenser is often caused by a frozen water "
            "line, a failed water inlet valve, a clogged water filter, or a "
            "faulty dispenser switch. Replace the clogged filter or failed inlet "
            "valve and clear any frozen line."
        ),
        namespace="repair-guides",
        category="refrigerator",
        intent="repair_guide",
    ),
]

# --- Dishwasher: troubleshooting / repair --------------------------------- #
DISHWASHER_REPAIR = [
    EvalCase(
        question="My dishwasher won't drain",
        reference=(
            "A dishwasher that won't drain is commonly caused by a clogged drain "
            "filter or hose, a failed drain pump, or a faulty check valve. Clean "
            "the filter and hose; if water still remains, replace the drain pump."
        ),
        namespace="repair-guides",
        category="dishwasher",
        intent="repair_guide",
    ),
    EvalCase(
        question="Dishwasher not cleaning dishes properly",
        reference=(
            "Poor cleaning is often due to clogged spray arms, a dirty filter, a "
            "failed wash pump or motor, or a faulty soap dispenser. Clean the "
            "spray arms and filter, and replace the wash pump if circulation is "
            "weak."
        ),
        namespace="repair-guides",
        category="dishwasher",
        intent="repair_guide",
    ),
    EvalCase(
        question="My dishwasher is leaking from the door",
        reference=(
            "Door leaks are usually caused by a worn or damaged door gasket/seal, "
            "a faulty door latch, or a defective gasket on the spray arm tower. "
            "Inspect and replace the door gasket and check the latch alignment."
        ),
        namespace="repair-guides",
        category="dishwasher",
        intent="repair_guide",
    ),
    EvalCase(
        question="Dishwasher won't start",
        reference=(
            "A dishwasher that won't start can be caused by a faulty door latch "
            "switch, a blown thermal fuse, a defective control board, or no "
            "power to the unit. Verify power and the door latch, then test the "
            "thermal fuse and control board."
        ),
        namespace="repair-guides",
        category="dishwasher",
        intent="repair_guide",
    ),
]

# --- Parts: name lookups -------------------------------------------------- #
PART_LOOKUPS = [
    EvalCase(
        question="water inlet valve for my refrigerator",
        reference=(
            "The water inlet valve is an electrically controlled valve that "
            "supplies water to the ice maker and water dispenser. It's replaced "
            "when the dispenser or ice maker stops getting water."
        ),
        namespace="parts",
        category="refrigerator",
        intent="search",
    ),
    EvalCase(
        question="refrigerator water filter",
        reference=(
            "The refrigerator water filter removes contaminants from the water "
            "supplied to the dispenser and ice maker, and should be replaced "
            "periodically (typically every six months) for clean water and flow."
        ),
        namespace="parts",
        category="refrigerator",
        intent="search",
    ),
    EvalCase(
        question="dishwasher drain pump",
        reference=(
            "The drain pump pushes wastewater out of the dishwasher at the end of "
            "a cycle. A failed drain pump leaves standing water in the tub and is "
            "replaced to restore draining."
        ),
        namespace="parts",
        category="dishwasher",
        intent="search",
    ),
    EvalCase(
        question="defrost thermostat",
        reference=(
            "The defrost thermostat monitors evaporator coil temperature and "
            "allows the defrost heater to turn on during the defrost cycle. A "
            "failed defrost thermostat causes frost buildup and is replaced to "
            "restore proper defrosting."
        ),
        namespace="parts",
        category="refrigerator",
        intent="search",
    ),
    EvalCase(
        question="dishwasher door latch",
        reference=(
            "The door latch secures the dishwasher door closed and signals the "
            "control that the door is shut so a cycle can start. A faulty latch "
            "can prevent the dishwasher from starting."
        ),
        namespace="parts",
        category="dishwasher",
        intent="search",
    ),
    EvalCase(
        question="evaporator fan motor",
        reference=(
            "The evaporator fan motor circulates cold air from the evaporator "
            "coils through the freezer and refrigerator compartments. A failed "
            "fan motor causes poor cooling and is replaced to restore airflow."
        ),
        namespace="parts",
        category="refrigerator",
        intent="search",
    ),
]

ALL_CASES = REFRIGERATOR_REPAIR + DISHWASHER_REPAIR + PART_LOOKUPS


def cases(subset: str = "all") -> list[EvalCase]:
    """Return eval cases. ``subset`` is one of: all | repair | parts | smoke."""
    if subset == "repair":
        return REFRIGERATOR_REPAIR + DISHWASHER_REPAIR
    if subset == "parts":
        return PART_LOOKUPS
    if subset == "smoke":
        # One of each kind for a quick, cheap validation run.
        return [REFRIGERATOR_REPAIR[0], DISHWASHER_REPAIR[0], PART_LOOKUPS[0]]
    return ALL_CASES
