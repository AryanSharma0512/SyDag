"""
SoilSignal ML command line. Run from ml/:

    uv run --project ../backend --group ml python -m soilsignal_ml <command>

    ingest    build the canonical dataset (imagery streamed, public context fetched)
    validate  data checks on the canonical dataset
    profile   write the dataset profile report
    train     cross-validate, tune and evaluate every model at every season cutoff
    report    write the experiment report from the training summaries
    export    write the selected models to backend/artifacts
    showcase  write the held-out plots' raw inputs to backend/data/practice for the API
    progressive  records only vs + imagery through TP1..TP6: early signal and scouting
                 (all options: python -m soilsignal_ml progressive --help)
    challenge inventory + join the challenge dataset -> ml/data/challenge/ (see
              soilsignal_ml/ingest/challenge.py); `--dataset challenge2022 ingest` then
              builds the canonical tables from it
"""

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["progressive"]:
        from soilsignal_ml.progressive.cli import main as progressive

        return progressive(argv[1:])
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
    sub.add_parser("showcase")
    sub.add_parser("progressive", help="early-signal experiments (see progressive --help)")
    challenge = sub.add_parser("challenge", help="inventory and join the challenge dataset")
    challenge.add_argument("--raw", default=None, help="local copy of the shared folder")
    challenge.add_argument("--out", default=None, help="output folder (ml/data/challenge)")
    source = challenge.add_mutually_exclusive_group()
    source.add_argument("--drive-listing", default=None, help="saved Drive listings folder")
    source.add_argument(
        "--inventory", default=None, help="drive_inventory.parquet to list files not on disk"
    )
    challenge.add_argument("--no-rasters", action="store_true", help="skip reading images")
    challenge.add_argument("--workers", type=int, default=4)
    challenge.add_argument("--limit", type=int, default=None, help="read at most N new images")
    sql = sub.add_parser("challenge-sql", help="CSV + psql load script for the challenge tables")
    sql.add_argument("--out", default=None, help="challenge output folder (ml/data/challenge)")
    args = parser.parse_args(argv)

    if args.command == "ingest":
        from soilsignal_ml.ingest.challenge_adapter import ChallengeDatasetAdapter
        from soilsignal_ml.ingest.context import add_public_context
        from soilsignal_ml.ingest.dataset_adapter import ADAPTERS

        adapters = {**ADAPTERS, ChallengeDatasetAdapter.name: ChallengeDatasetAdapter}
        dataset = adapters[args.dataset]().build()
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
    elif args.command == "showcase":
        from soilsignal_ml.export.showcase import write_bundle

        print(f"wrote {write_bundle(args.dataset)}")
    elif args.command == "challenge":
        from pathlib import Path

        from soilsignal_ml.ingest import challenge as ch
        from soilsignal_ml.ingest.challenge_report import write_outputs

        raw = Path(args.raw) if args.raw else ch.RAW_ROOT
        out = Path(args.out) if args.out else ch.OUT_ROOT
        tables = ch.build(
            raw_root=raw,
            drive_listing=Path(args.drive_listing) if args.drive_listing else None,
            inventory=Path(args.inventory) if args.inventory else None,
            out_root=out,
            read_rasters=not args.no_rasters,
            workers=args.workers,
            limit=args.limit,
        )
        manifest = write_outputs(tables, out, raw)
        for name, schema in manifest["outputs"].items():
            print(f"  {name}: {schema['rows']} rows")
        print(f"  anomalies: {len(manifest['anomalies'])} (see {out / 'challenge_manifest.json'})")
    elif args.command == "challenge-sql":
        from pathlib import Path

        from soilsignal_ml.ingest.challenge import OUT_ROOT
        from soilsignal_ml.ingest.challenge_postgres import export_postgres

        print(f"wrote {export_postgres(Path(args.out) if args.out else OUT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
