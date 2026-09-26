"""
Command line for the progressive early-signal experiments. Run from ml/:

    uv run --project ../backend --group ml python progressive_experiment.py --help

Inputs (pick one source):
    --imagery-table T [--plots P]
                            Agent 2's progressive table (satellite_features.parquet)
    --plots P [--tp-features F | --tp-observations O] [--acquisitions A]
                            Agent 1 / Agent 2 files (CSV or Parquet), see contract.py
    --canonical NAME        an ingested canonical dataset (e.g. shrestha2024)
    --synthetic             the synthetic fixture (tests and templates only)
"""

import argparse
import sys
from pathlib import Path

from soilsignal_ml import ML_ROOT
from soilsignal_ml.progressive import contract, report
from soilsignal_ml.progressive.runner import CONFIG, RunConfig, run

DEFAULT_OUT = ML_ROOT / "experiments" / "progressive"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="progressive_experiment",
        description="How early does satellite imagery add to a yield forecast? "
        "Records only vs + TP1 ... TP6 under grouped validation.",
    )
    src = p.add_argument_group("inputs")
    src.add_argument(
        "--imagery-table",
        help="Agent 2's satellite_features.parquet (soilsignal_ml.imagery); records and yield "
        "come from its records_only rows unless --plots is also given",
    )
    src.add_argument("--include-qa", action="store_true", help="use its QA columns as features")
    src.add_argument("--plots", help="Agent 1 plots table (CSV/Parquet)")
    src.add_argument("--tp-features", help="Agent 2 CUMULATIVE features (long or wide)")
    src.add_argument("--tp-observations", help="per-pass values; cumulative features built here")
    src.add_argument("--acquisitions", help="site_id, year, tp, date (DateofCollection)")
    src.add_argument("--value-columns", nargs="*", help="per-pass columns to accumulate")
    src.add_argument(
        "--allow-columns", nargs="*", default=[], help="feature names to allow despite the guard"
    )
    src.add_argument("--canonical", help="canonical dataset name under ml/data/processed/")
    src.add_argument("--synthetic", action="store_true", help="synthetic fixture (NOT a result)")
    src.add_argument("--synthetic-scale", type=float, default=1.0)
    src.add_argument("--synthetic-2023", action="store_true", help="add an invented 2023 season")
    src.add_argument("--name", help="dataset name for the outputs")

    exp = p.add_argument_group("experiment")
    exp.add_argument("--config", default=str(CONFIG), help="YAML config (default progressive.yaml)")
    exp.add_argument("--stage-mode", choices=["tp", "dap", "calendar"])
    exp.add_argument(
        "--stages", nargs="*", help="tp: 1 2 3 | dap: 45 60 75 | calendar: 07-15 07-31"
    )
    exp.add_argument("--models", nargs="*", help="e.g. mean ridge catboost")
    exp.add_argument("--primary-model")
    exp.add_argument(
        "--validation", nargs="*", help="auto, or: temporal site year site_year field random"
    )
    exp.add_argument("--test-year", type=int, help="temporal scheme: season to test on")
    exp.add_argument("--no-nested", action="store_true", help="fast, in-sample intervals")
    exp.add_argument("--no-cqr", action="store_true", help="skip the per-plot (CQR) intervals")
    exp.add_argument("--fast", action="store_true", help="fewer trees / iterations (smoke runs)")
    exp.add_argument("--seed", type=int)

    out = p.add_argument_group("outputs")
    out.add_argument("--out", help=f"output directory (default {DEFAULT_OUT}/<name>)")
    out.add_argument("--ablation-stage", help="stage for imagery_ablation.json (default: last)")
    out.add_argument("--dataset-label", help='e.g. "Challenge data" (shown on the dashboard)')
    out.add_argument(
        "--publish", action="store_true", help="copy imagery_ablation.json to backend/artifacts"
    )
    return p


FAST_PARAMS = {
    "random_forest": {"n_estimators": 100},
    "hist_gradient_boosting": {"max_iter": 120},
    "catboost": {"iterations": 200},
    "xgboost": {"n_estimators": 150},
    "lightgbm": {"n_estimators": 150},
}


def load_data(args) -> contract.ExperimentData:
    files = bool(args.plots or args.imagery_table)
    sources = sum(bool(x) for x in (files, args.canonical, args.synthetic))
    if sources != 1:
        raise SystemExit(
            "choose exactly one input: --imagery-table / --plots ..., --canonical NAME "
            "or --synthetic"
        )
    if args.synthetic:
        from soilsignal_ml.progressive.synthetic import synthetic_data

        return synthetic_data(scale=args.synthetic_scale, with_2023=args.synthetic_2023)
    if args.canonical:
        return contract.from_canonical(args.canonical, args.value_columns)
    return contract.from_files(
        args.name or Path(args.plots or args.imagery_table).parent.name or "dataset",
        args.plots,
        imagery_table=args.imagery_table,
        include_qa=args.include_qa,
        tp_features=args.tp_features,
        tp_observations=args.tp_observations,
        acquisitions=args.acquisitions,
        value_columns=args.value_columns,
        allow_columns=set(args.allow_columns),
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    data = load_data(args)
    if args.name:
        data.name = args.name
    overrides = {
        "stage_mode": args.stage_mode,
        "stage_cutoffs": args.stages,
        "models": args.models,
        "primary_model": args.primary_model,
        "test_year": args.test_year,
        "seed": args.seed,
    }
    if args.validation and args.validation != ["auto"]:
        overrides["schemes"] = args.validation
    cfg = RunConfig.load(Path(args.config), **overrides)
    if args.no_nested:
        cfg.nested_intervals = False
    if args.no_cqr:
        cfg.cqr = False
    if args.fast:
        cfg.params = {m: {**cfg.params.get(m, {}), **p} for m, p in FAST_PARAMS.items()}
        cfg.n_boot = min(cfg.n_boot, 500)
    if cfg.primary_model not in cfg.models:
        cfg.models.append(cfg.primary_model)

    result = run(data, cfg)
    slug = data.name.replace(" ", "_")
    out_dir = Path(args.out) if args.out else DEFAULT_OUT / slug
    written = report.write_outputs(result, out_dir, args.ablation_stage, args.dataset_label)
    print(f"\nwrote {len(written)} files to {out_dir}")
    crit = result["criteria"]
    print(
        f"earliest stage passing all checks: {crit['earliest_candidate'] or 'none'}; "
        f"passing accuracy checks: {', '.join(crit['stages_passing_accuracy_checks']) or 'none'}"
    )
    if args.publish:
        try:
            print(f"published {report.publish(result, out_dir)}")
        except report.PublishError as err:
            print(f"not published: {err}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
