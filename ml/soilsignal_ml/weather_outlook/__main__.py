"""
Weather outlook command line. Run from ml/:

    uv run --project ../backend --group ml python -m soilsignal_ml.weather_outlook <command>

    history   build the weather history libraries (supplied, long), run season QC and
              publish them to backend/data/weather_history/ with their manifests
    outlook   one outlook as JSON (+ the trajectories as Parquet)
    backtest  leave-one-season-out backtest -> ml/experiments/weather_outlook/<library>/
    yield     couple an outlook to an exported yield model on the practice bundle (Layer 2)
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path


def _horizon(value: str) -> int | str:
    return "season" if value == "season" else int(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="soilsignal_ml.weather_outlook", description=__doc__.split("\n\n")[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    hist = sub.add_parser("history", help="build, check and publish the weather libraries")
    hist.add_argument("--library", choices=["supplied", "long", "all"], default="all")
    hist.add_argument("--refresh", action="store_true", help="re-download cached records")
    hist.add_argument(
        "--end", type=date.fromisoformat, default=None, help="last day to fetch (long library)"
    )

    one = sub.add_parser("outlook", help="one outlook as JSON")
    one.add_argument("--library", default="long")
    one.add_argument("--site", required=True)
    one.add_argument("--as-of", type=date.fromisoformat, required=True)
    one.add_argument("--horizon", type=_horizon, default=60, help="days, or 'season'")
    one.add_argument("--planting", type=date.fromisoformat, default=None)
    one.add_argument("--json", type=Path, default=None, help="write the contract here")
    one.add_argument("--parquet", type=Path, default=None, help="write trajectories here")

    bt = sub.add_parser("backtest", help="leave-one-season-out backtest")
    bt.add_argument("--library", default="long")
    bt.add_argument("--sites", nargs="*", default=None)
    bt.add_argument(
        "--report-only", action="store_true", help="rebuild the report from saved cases.csv"
    )

    yl = sub.add_parser("yield", help="couple an outlook to an exported yield model")
    yl.add_argument("--library", default="long")
    yl.add_argument("--bundle", type=Path, default=None, help="showcase bundle (practice data)")
    yl.add_argument("--plot", default=None, help="plot id in the bundle (default: first)")
    yl.add_argument("--model", default=None, help="model id (default: every artifact)")
    yl.add_argument("--as-of", type=date.fromisoformat, required=True)

    args = parser.parse_args(argv)

    if args.command == "history":
        from soilsignal_ml.weather_outlook.cli import run_history

        return run_history(args.library, args.refresh, args.end)
    if args.command == "outlook":
        from soilsignal_ml.weather_outlook.cli import run_outlook

        doc = run_outlook(
            args.library, args.site, args.as_of, args.horizon, args.planting, args.parquet
        )
        text = json.dumps(doc, indent=2)
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(text + "\n")
        print(text)
        return 0
    if args.command == "backtest":
        from soilsignal_ml.weather_outlook.backtest import run_backtest

        run_backtest(args.library, args.sites, args.report_only)
        return 0
    if args.command == "yield":
        from soilsignal_ml.weather_outlook.cli import run_yield

        return run_yield(args.library, args.bundle, args.plot, args.model, args.as_of)
    return 1


if __name__ == "__main__":
    sys.exit(main())
