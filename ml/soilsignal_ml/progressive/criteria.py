"""
"Earliest useful forecast": five checks per imagery stage, on the headline validation and
the primary model. Each check reports its value, its threshold and pass / fail, so the
team can see why a stage qualifies and choose the narrative; nothing here hardcodes a
winner, and the lowest-MAE stage is not automatically the answer.

    1. beats_records   MAE at least `min_mae_reduction_pct` below records only, and the
                       paired bootstrap interval for the reduction excludes zero
    2. consistent      imagery lowers MAE in at least `min_group_win_share` of the held-out
                       site-seasons, and in at least `min_model_agreement` of the candidate
                       models (not one model's luck)
    3. calibrated      90% interval coverage within `coverage_tolerance` of nominal, and
                       no held-out site-season below `min_group_coverage`
    4. scouting        recall of the bottom quartile at the `scouting_budget`, using the
                       `scouting_ranker` method, beats the same method on records only by
                       `min_recall_gain`, and beats random
    5. early           median lead time to harvest of at least `min_lead_days`

The earliest candidate is the first stage (in season order) that passes all five. The
stages that pass the accuracy checks (1 and 2) are listed separately, as partial evidence.
"""

import numpy as np

DEFAULTS = {
    "min_mae_reduction_pct": 5.0,
    "require_ci_above_zero": True,
    "min_group_win_share": 0.67,
    "min_model_agreement": 0.75,
    "coverage_tolerance": 0.05,
    "min_group_coverage": 0.75,
    "scouting_budget": 0.20,
    "min_recall_gain": 0.05,
    # Ranking judged by check 4, fixed in advance: forecast, lower_bound or relative_forecast.
    "scouting_ranker": "relative_forecast",
    "min_lead_days": 30,
}
NAMES = ("beats_records", "consistent", "calibrated", "scouting", "early")


def _check(passed, value, threshold, detail: str) -> dict:
    return {
        "passed": None if passed is None else bool(passed),
        "value": value,
        "threshold": threshold,
        "detail": detail,
    }


def _finite(x) -> bool:
    return x is not None and np.isfinite(x)


def evaluate(rows, scouting_rows, timing, stages, scheme: str, cfg) -> dict:
    t = {**DEFAULTS, **(cfg.criteria or {})}
    primary = cfg.primary_model
    by = {(r["stage"], r["model"]): r for r in rows if r["validation"] == scheme}
    budget = t["scouting_budget"]
    recall = {
        (s["stage"], s["ranker"]): s
        for s in scouting_rows
        if s["validation"] == scheme and abs(s["budget"] - budget) < 1e-9
    }
    candidates = [m for m in cfg.models if m != "mean"]
    per_stage = []
    for stage in stages:
        if not stage.uses_imagery:
            continue
        r = by.get((stage.key, primary))
        if r is None:
            continue
        checks = {}
        pct = r.get("pct_mae_reduction_vs_records")
        ci_low = r.get("delta_mae_ci_low")
        ok = _finite(pct) and pct >= t["min_mae_reduction_pct"]
        if t["require_ci_above_zero"]:
            ok = ok and _finite(ci_low) and ci_low > 0
        checks["beats_records"] = _check(
            ok,
            {
                "pct_mae_reduction": pct,
                "delta_mae": r.get("delta_mae_vs_records"),
                "ci_low": ci_low,
            },
            {"min_pct": t["min_mae_reduction_pct"], "ci_above_zero": t["require_ci_above_zero"]},
            f"MAE {r['mae']:.1f} vs records-only "
            f"{r['mae'] + r.get('delta_mae_vs_records', np.nan):.1f} bu/ac",
        )

        wins, n_groups = r.get("group_wins"), r.get("n_groups")
        share = wins / n_groups if n_groups else float("nan")
        improving = [
            m
            for m in candidates
            if (stage.key, m) in by and by[(stage.key, m)].get("delta_mae_vs_records", -1) > 0
        ]
        ran = [m for m in candidates if (stage.key, m) in by]
        agreement = len(improving) / len(ran) if ran else float("nan")
        checks["consistent"] = _check(
            _finite(share)
            and share >= t["min_group_win_share"]
            and _finite(agreement)
            and agreement >= t["min_model_agreement"],
            {"group_win_share": share, "model_agreement": agreement, "improving_models": improving},
            {
                "min_group_win_share": t["min_group_win_share"],
                "min_model_agreement": t["min_model_agreement"],
            },
            f"lower MAE in {wins}/{n_groups} held-out site-seasons, "
            f"{len(improving)}/{len(ran)} models",
        )

        cov, cov_min = r.get("coverage"), r.get("coverage_min_group")
        checks["calibrated"] = _check(
            None
            if not _finite(cov)
            else abs(cov - cfg.level) <= t["coverage_tolerance"]
            and _finite(cov_min)
            and cov_min >= t["min_group_coverage"],
            {"coverage": cov, "worst_group_coverage": cov_min, "width": r.get("interval_width")},
            {
                "nominal": cfg.level,
                "tolerance": t["coverage_tolerance"],
                "min_group": t["min_group_coverage"],
            },
            "nested conformal interval around the primary model",
        )

        fc = recall.get((stage.key, t["scouting_ranker"]))
        rec = recall.get((stage.key, "records_only"))
        if fc and rec:
            gain = fc["recall"] - rec["recall"]
            checks["scouting"] = _check(
                gain >= t["min_recall_gain"] and fc["recall"] > fc["random_recall"],
                {
                    "recall": fc["recall"],
                    "records_recall": rec["recall"],
                    "random_recall": fc["random_recall"],
                    "gain": gain,
                },
                {
                    "budget": budget,
                    "min_gain": t["min_recall_gain"],
                    "ranker": t["scouting_ranker"],
                },
                f"bottom-quartile recall at {budget:.0%} budget ({t['scouting_ranker']})",
            )
        else:
            checks["scouting"] = _check(None, None, None, "no scouting evaluation")

        lead = timing.get(stage.key, {}).get("lead_days_median")
        checks["early"] = _check(
            None if lead is None else lead >= t["min_lead_days"],
            {"lead_days_median": lead, "dap_median": timing.get(stage.key, {}).get("dap_median")},
            {"min_lead_days": t["min_lead_days"]},
            timing.get(stage.key, {}).get("harvest_basis", "no acquisition dates"),
        )
        passed = [c["passed"] for c in checks.values()]
        per_stage.append(
            {
                "stage": stage.key,
                "label": stage.label,
                "order": stage.order,
                "checks": checks,
                "all_passed": all(p is True for p in passed),
                "n_passed": sum(p is True for p in passed),
                "n_unknown": sum(p is None for p in passed),
            }
        )
    earliest = next((s for s in per_stage if s["all_passed"]), None)
    accuracy_only = [
        s["stage"]
        for s in per_stage
        if s["checks"]["beats_records"]["passed"] and s["checks"]["consistent"]["passed"]
    ]
    return {
        "validation": scheme,
        "model": primary,
        "thresholds": t,
        "stages": per_stage,
        "earliest_candidate": earliest["stage"] if earliest else None,
        "stages_passing_accuracy_checks": accuracy_only,
        "note": "Evidence for the team's decision, not a verdict: thresholds are in "
        "configs/progressive.yaml and every value is reported.",
    }
