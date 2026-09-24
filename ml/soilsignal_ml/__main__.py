"""
SoilSignal ML command line. Run from ml/:

    uv run --project ../backend --group ml python -m soilsignal_ml <command>

    ingest    build the canonical dataset (imagery streamed, public context fetched)
    validate  data checks on the canonical dataset
    profile   write the dataset profile report
    train     cross-validate, tune and evaluate every model at every season cutoff
    report    write the experiment report from the training summaries
    export    write the selected models to backend/artifacts and the showcase bundle
"""

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="soilsignal_ml", description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset", default="shrestha2024")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest")
    sub.add_parser("context", help="re-fetch public context for an ingested dataset")
    sub.add_parser("validate")
    sub.add_parser("profile")
    train = sub.add_parser("train")
    train.add_argument("--trials", type=int, default=None, help="Optuna trials per model")
    train.add_argument("--cutoffs", nargs="*", help="config names, e.g. july august")
    sub.add_parser("report")
    sub.add_parser("export")
    args = parser.parse_args(argv)

    if args.command == "ingest":
        from soilsignal_ml.ingest.context import add_public_context
        from soilsignal_ml.ingest.dataset_adapter import ADAPTERS

        dataset = ADAPTERS[args.dataset]().build()
        dataset = add_public_context(dataset)
        print(f"saved {dataset.save()}")
    elif args.command == "context":
        from soilsignal_ml.ingest.canonical import CanonicalDataset
        from soilsignal_ml.ingest.context import add_public_context

        print(f"saved {add_public_context(CanonicalDataset.load(args.dataset)).save()}")
    elif args.command == "validate":
        from soilsignal_ml.ingest.canonical import CanonicalDataset
        from soilsignal_ml.ingest.validate import validate

        problems = validate(CanonicalDataset.load(args.dataset))
        for p in problems:
            print(f"- {p}")
        print("ok" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    elif args.command == "profile":
        from soilsignal_ml.ingest.profile import write_profile

        print(f"wrote {write_profile(args.dataset)}")
    elif args.command == "train":
        from soilsignal_ml.models.train import run_training

        run_training(args.dataset, cutoffs=args.cutoffs, trials=args.trials)
    elif args.command == "report":
        from soilsignal_ml.evaluation.reports import write_report

        print(f"wrote {write_report()}")
    elif args.command == "export":
        from soilsignal_ml.export.export_to_backend import export

        export(args.dataset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
