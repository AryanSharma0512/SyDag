"""
Information stages: what a forecast could have used at each point in the season.

    records   Records only (hybrid, nitrogen, irrigation, planting date). No imagery.
    tp        Records + imagery through TP1, TP1-TP2, ..., TP1-TP6. TP labels are the
              order of passes at each site, not a date: TP2 can be weeks apart between
              sites, so every stage also reports its acquisition dates and days after
              planting.
    dap       Records + every pass acquired by N days after planting (per plot).
    calendar  Records + every pass acquired by a calendar date (MM-DD) each season.

A stage maps each plot to the last pass it may see (0 = none). Features then come from
that pass's CUMULATIVE row, which by contract used passes 1..k only.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from soilsignal_ml.progressive.contract import ExperimentData

DEFAULT_ASSUMED_HARVEST = "10-15"


@dataclass(eq=False)
class Stage:
    key: str  # "records", "tp3", "dap60", "cal0731"
    label: str  # "Records only", "+ TP1-TP3"
    order: int
    uses_imagery: bool
    visible_tp: pd.Series  # per plot (index = plot_id): last pass the stage may use, 0 = none

    @property
    def short(self) -> str:
        return "Records" if not self.uses_imagery else self.key.upper()


def _available(data: ExperimentData) -> dict[str, list[int]]:
    return data.tp_features.groupby("plot_id")["tp"].apply(lambda s: sorted(s.tolist())).to_dict()


def _visible(avail: list[int], allowed) -> int:
    ok = [t for t in avail if allowed(t)]
    return max(ok) if ok else 0


def _pass_dates(data: ExperimentData) -> pd.DataFrame:
    """Per plot and pass: acquisition date and days after planting."""
    p = data.plots[["plot_id", "site_id", "year", "planting_date"]]
    frame = data.tp_features[["plot_id", "tp"]].merge(p, on="plot_id")
    frame = frame.merge(data.acquisitions, on=["site_id", "year", "tp"], how="left")
    frame["dap"] = (frame["date"] - frame["planting_date"]).dt.days
    return frame


def build_stages(
    data: ExperimentData, mode: str = "tp", cutoffs: list | None = None
) -> list[Stage]:
    plot_ids = data.plots["plot_id"]
    avail = _available(data)
    stages = [Stage("records", "Records only", 0, False, pd.Series(0, index=plot_ids.values))]

    def per_plot(allowed_for_plot) -> pd.Series:
        return pd.Series(
            [_visible(avail.get(pid, []), allowed_for_plot(pid)) for pid in plot_ids],
            index=plot_ids.values,
        )

    if mode == "tp":
        tps = cutoffs or data.tps
        for i, k in enumerate(tps, 1):
            k = int(k)
            label = "+ TP1" if k == 1 else f"+ TP1-TP{k}"
            stages.append(
                Stage(f"tp{k}", label, i, True, per_plot(lambda _, k=k: lambda t: t <= k))
            )
    elif mode in ("dap", "calendar"):
        if data.acquisitions.empty:
            raise ValueError(f"stage mode {mode!r} needs acquisition dates")
        passes = _pass_dates(data)
        by_plot = {pid: g for pid, g in passes.groupby("plot_id")}
        years = data.plots.set_index("plot_id")["year"]
        for i, cut in enumerate(cutoffs or [], 1):
            if mode == "dap":
                days = int(cut)

                def allowed(pid, days=days):
                    g = by_plot.get(pid)
                    ok = set() if g is None else set(g.loc[g["dap"] <= days, "tp"])
                    return lambda t: t in ok

                stages.append(
                    Stage(f"dap{days}", f"+ imagery by {days} DAP", i, True, per_plot(allowed))
                )
            else:
                mm, dd = (int(x) for x in str(cut).split("-"))

                def allowed(pid, mm=mm, dd=dd):
                    g = by_plot.get(pid)
                    cutoff = pd.Timestamp(date(int(years[pid]), mm, dd))
                    ok = set() if g is None else set(g.loc[g["date"] <= cutoff, "tp"])
                    return lambda t: t in ok

                key = f"cal{mm:02d}{dd:02d}"
                label = f"+ imagery by {date(2000, mm, dd):%b} {dd}"
                stages.append(Stage(key, label, i, True, per_plot(allowed)))
    else:
        raise ValueError(f"unknown stage mode {mode!r} (tp, dap, calendar)")
    return stages


def stage_frame(data: ExperimentData, stage: Stage) -> tuple[pd.DataFrame, list[str]]:
    """Plots with their records and this stage's imagery features; the imagery columns
    that carry information at this stage."""
    frame = data.plots.copy()
    if not stage.uses_imagery:
        return frame, []
    frame["_tp"] = frame["plot_id"].map(stage.visible_tp).fillna(0).astype(int)
    feats = data.tp_features.rename(columns={"tp": "_tp"})
    frame = frame.merge(feats, on=["plot_id", "_tp"], how="left")
    cols = [
        c
        for c in data.imagery_columns
        if frame[c].notna().any() and frame[c].nunique(dropna=True) > 1
    ]
    return frame.drop(columns=["_tp"]), cols


def assumed_harvest(data: ExperimentData, mmdd: str = DEFAULT_ASSUMED_HARVEST) -> pd.Series:
    """Per plot harvest date: the recorded one if Agent 1 provides it, else MM-DD that year."""
    mm, dd = (int(x) for x in mmdd.split("-"))
    nominal = data.plots["year"].map(lambda y: pd.Timestamp(date(int(y), mm, dd)))
    if "harvest_date" in data.plots:
        nominal = data.plots["harvest_date"].fillna(nominal)
    return pd.Series(nominal.values, index=data.plots["plot_id"].values)


def stage_timing(
    data: ExperimentData, stage: Stage, harvest_mmdd: str = DEFAULT_ASSUMED_HARVEST
) -> dict:
    """When the stage's information arrives: acquisition dates, days after planting, number
    of passes, and lead time to harvest, overall and per site-year."""
    out = {"stage": stage.key, "label": stage.label, "uses_imagery": stage.uses_imagery}
    if not stage.uses_imagery:
        return out | {"passes_mean": 0.0, "per_site_year": []}
    p = data.plots.set_index("plot_id")
    vis = stage.visible_tp.reindex(p.index).fillna(0).astype(int)
    passes = data.tp_features.groupby("plot_id")["tp"].apply(list)
    n_passes = pd.Series(
        [sum(t <= v for t in passes.get(pid, [])) for pid, v in vis.items()], index=vis.index
    )
    out["passes_mean"] = float(n_passes.mean())
    out["share_with_imagery"] = float((vis > 0).mean())
    if data.acquisitions.empty:
        return out | {"per_site_year": []}
    frame = pd.DataFrame(
        {"site_id": p["site_id"], "year": p["year"], "tp": vis, "planting": p["planting_date"]}
    )
    frame = frame.merge(data.acquisitions, on=["site_id", "year", "tp"], how="left")
    frame.index = p.index
    frame["dap"] = (frame["date"] - frame["planting"]).dt.days
    harvest = assumed_harvest(data, harvest_mmdd).reindex(p.index)
    frame["lead_days"] = (harvest - frame["date"]).dt.days
    have = frame[frame["date"].notna()]
    if have.empty:
        return out | {"per_site_year": []}

    def q(s: pd.Series, f) -> float | None:
        s = s.dropna()
        return None if s.empty else float(f(s))

    dates = have["date"]
    out |= {
        "acq_date_min": dates.min().date().isoformat(),
        "acq_date_median": dates.sort_values().iloc[len(dates) // 2].date().isoformat(),
        "acq_date_max": dates.max().date().isoformat(),
        "dap_min": q(have["dap"], np.min),
        "dap_median": q(have["dap"], np.median),
        "dap_max": q(have["dap"], np.max),
        "lead_days_median": q(have["lead_days"], np.median),
        "lead_days_min": q(have["lead_days"], np.min),
        "harvest_basis": "recorded harvest_date"
        if "harvest_date" in data.plots and data.plots["harvest_date"].notna().all()
        else f"assumed {harvest_mmdd} each season",
    }
    per = []
    for (site, year), g in frame.groupby(["site_id", "year"]):
        tps = g["tp"][g["tp"] > 0]
        per.append(
            {
                "site_id": site,
                "year": int(year),
                "last_pass": int(tps.max()) if len(tps) else 0,
                "date": g["date"].dropna().max().date().isoformat()
                if g["date"].notna().any()
                else None,
                "dap_median": q(g["dap"], np.median),
                "lead_days_median": q(g["lead_days"], np.median),
            }
        )
    out["per_site_year"] = per
    return out
