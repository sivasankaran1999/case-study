"""Standalone demo for the agentic discovery engine.

Run from the backend/ directory:

    python -m scraper.demo_agentic
    python -m scraper.demo_agentic "ice maker not working" --model WRF560SEHZ00 --category refrigerator

It prints each AGENT DECISION (plan -> fetch -> rank -> index) live so you can
*see* the agency, then a compact summary of what got upserted into Pinecone.

This bypasses the ENABLE_AGENTIC_DISCOVERY flag on purpose — the flag guards the
live chat path; the demo is meant to exercise the engine directly.
"""

import argparse
import json

from scraper.agentic_discovery import discover


# A few representative goals that exercise different planner branches.
_PRESETS = [
    {
        "goal": "ice maker not making ice on my Whirlpool fridge",
        "signals": {
            "model_number": "WRF560SEHZ00",
            "brand": "Whirlpool",
            "category": "refrigerator",
            "symptom": "ice maker not working",
        },
    },
    {
        "goal": "dishwasher not draining, need the drain pump",
        "signals": {"category": "dishwasher", "symptom": "not draining", "part_name": "drain pump"},
    },
]


def _print_report(report: dict):
    print("\n" + "-" * 60)
    print("SUMMARY")
    print("-" * 60)
    print(f"  Goal:           {report['goal']}")
    print(f"  Backend:        {report.get('backend')}")
    print(f"  Plan:           {json.dumps(report.get('plan', []))}")
    print(f"  Pages fetched:  {report['pages_fetched']}")
    print(f"  Parts indexed:  {report['indexed_parts']}")
    print(f"  Repairs indexed:{report['indexed_repairs']}")
    print(f"  Models cached:  {report['models_cached']}")
    print(f"  Elapsed:        {report['elapsed_s']}s")
    print(f"  Stopped reason: {report['stopped_reason']}")
    print("-" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Agentic discovery demo")
    parser.add_argument("goal", nargs="?", help="free-text goal; omit to run presets")
    parser.add_argument("--model", default="", help="model number signal")
    parser.add_argument("--brand", default="", help="brand signal")
    parser.add_argument("--category", default="", help="refrigerator|dishwasher")
    parser.add_argument("--symptom", default="", help="symptom signal")
    parser.add_argument("--part", default="", help="part name signal")
    args = parser.parse_args()

    if args.goal:
        signals = {
            "model_number": args.model,
            "brand": args.brand,
            "category": args.category,
            "symptom": args.symptom,
            "part_name": args.part,
        }
        _print_report(discover(args.goal, signals=signals))
    else:
        print("No goal given — running presets.\n")
        for preset in _PRESETS:
            _print_report(discover(preset["goal"], signals=preset["signals"]))


if __name__ == "__main__":
    main()
