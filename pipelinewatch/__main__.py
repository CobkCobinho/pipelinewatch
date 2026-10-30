import argparse
import json
from datetime import date
from pathlib import Path

from .core import ROOT, SCENARIOS, demo, export, run_pipeline


def main():
    parser = argparse.ArgumentParser(description="PipelineWatch — dados e telemetria sintéticos")
    parser.add_argument("command", choices=("demo", "run", "export"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--batches", type=int, default=72)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--component", type=int, default=0, choices=range(8))
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    parser.add_argument("--date", type=date.fromisoformat)
    args = parser.parse_args()
    if args.command == "demo":
        snapshot = demo(args.root, args.batches, args.seed, args.date)
        print(json.dumps({"runs": len(snapshot["runs"]), "synthetic": True}))
    elif args.command == "run":
        run = run_pipeline(args.root, seed=args.seed, count=args.count,
                           component_index=args.component, scenario=args.scenario, event_date=args.date)
        export(args.root)
        print(json.dumps(run))
    else:
        print(json.dumps({"runs": len(export(args.root)["runs"])}))


if __name__ == "__main__":
    main()
