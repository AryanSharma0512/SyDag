"""
Imagery features command line. Run from ml/:

    uv run --project ../backend --group ml python -m soilsignal_ml.imagery <command>

    run         extract, check and build the progressive tables (resumable)
    benchmark   time extraction on a sample and extrapolate to the full set
    dictionary  write the feature dictionary
    synthetic   write a small fake dataset in the challenge layout (tests, demos)
"""

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="soilsignal_ml.imagery", description=__doc__.split("\n\n")[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="extract features and build the progressive tables")
    run.add_argument(
        "--data-root",
        type=Path,
        required=True,
        help="folder holding Satellite/, UAV/, GroundTruth/",
    )
    run.add_argument(
        "--out", type=Path, default=None, help="output folder (default ml/data/interim/imagery)"
    )
    run.add_argument(
        "--manifest", type=Path, help="Agent 1 image manifest (CSV/Parquet with a path column)"
    )
    run.add_argument(
        "--plots", type=Path, help="plots table (canonical plots.csv or the ground-truth CSV)"
    )
    run.add_argument(
        "--acquisitions", type=Path, help="acquisition dates (tidy table or DateofCollection.xlsx)"
    )
    run.add_argument("--workers", type=int, default=None, help="processes (default: all CPUs)")
    run.add_argument(
        "--limit",
        type=int,
        default=None,
        help="only this many satellite images, spread over sites/TPs",
    )
    run.add_argument(
        "--bands", nargs="+", default=None, help="band order when a file has no band descriptions"
    )
    run.add_argument(
        "--reflectance-scale", type=float, default=None, help="default: 10000 for integer data"
    )
    run.add_argument("--no-uav", action="store_true")
    run.add_argument("--no-visual-qa", action="store_true")
    run.add_argument("--retry-errors", action="store_true", help="re-read files that failed before")
    run.add_argument("--note", default="", help="one line added to the quality report")

    bench = sub.add_parser("benchmark", help="time extraction and extrapolate")
    bench.add_argument("--data-root", type=Path, required=True)
    bench.add_argument("--out", type=Path, default=None)
    bench.add_argument("--sample", type=int, default=200)
    bench.add_argument("--workers", type=int, default=None)

    dic = sub.add_parser("dictionary", help="write the feature dictionary")
    dic.add_argument("--out", type=Path, default=None)

    syn = sub.add_parser("synthetic", help="write a small fake dataset")
    syn.add_argument("root", type=Path)
    syn.add_argument("--plots-per-site", type=int, default=12)
    syn.add_argument("--no-defects", action="store_true")
    syn.add_argument(
        "--uav-scale", type=int, default=3, help="UAV image size vs satellite, per side"
    )

    args = parser.parse_args(argv)
    from soilsignal_ml.imagery.pipeline import DEFAULT_OUT

    if args.command == "run":
        from soilsignal_ml.imagery.pipeline import run as run_pipeline

        run_pipeline(
            args.data_root,
            args.out or DEFAULT_OUT,
            manifest=args.manifest,
            plots=args.plots,
            acquisitions=args.acquisitions,
            workers=args.workers,
            limit=args.limit,
            band_order=tuple(args.bands) if args.bands else None,
            reflectance_scale=args.reflectance_scale,
            uav=not args.no_uav,
            visual_qa=not args.no_visual_qa,
            retry_errors=args.retry_errors,
            note=args.note,
        )
    elif args.command == "benchmark":
        from soilsignal_ml.imagery.pipeline import benchmark

        benchmark(args.data_root, args.out or DEFAULT_OUT, args.sample, args.workers)
    elif args.command == "dictionary":
        from soilsignal_ml.imagery.dictionary import dictionary_markdown

        path = args.out or (DEFAULT_OUT / "reports" / "feature_dictionary.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dictionary_markdown())
        print(f"wrote {path}")
    elif args.command == "synthetic":
        from soilsignal_ml.imagery.synthetic import write_synthetic

        info = write_synthetic(
            args.root,
            plots_per_site=args.plots_per_site,
            defects=not args.no_defects,
            uav_scale=args.uav_scale,
        )
        print(f"wrote {info['plots']} plots to {args.root}; defects: {sorted(info['defects'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
