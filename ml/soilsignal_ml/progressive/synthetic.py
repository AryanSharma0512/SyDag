"""
SYNTHETIC fixture for exercising the progressive experiments. NOT A RESULT.

It copies the practice dataset's *structure* so every code path meets realistic inputs:
the three sites on the team Drive (Ames, Crawfordsville, Lincoln), their real satellite
acquisition dates and planting dates, their site yield means and spreads, nitrogen rates
confounded with experiment blocks, 84 hybrids, and per-site NDVI-yield correlations by
time point taken from ml/experiments/reports/dataset_profile.md (including Lincoln's sign
flip after the drought). Yields and imagery are random draws. Any number produced from
this fixture says only that the code runs; outputs are stamped `synthetic: true` and
the publish step refuses them.
"""

import numpy as np
import pandas as pd

from soilsignal_ml.progressive.contract import ExperimentData, from_frames

SITES = {
    "Ames": {
        "lat": 42.014,
        "lon": -93.734,
        "planting": "05-22",
        "n": 487,
        "sd": 31.8,
        "blocks": {75: 145.2, 150: 122.1, 250: 123.6},
        "dates": ["07-15", "07-23", "08-10", "08-31", "09-11", "09-24"],
        "ndvi": [0.78, 0.81, 0.79, 0.78, 0.74, 0.52],
        "rho": [0.06, 0.31, 0.57, 0.57, 0.36, 0.16],
    },
    "Crawfordsville": {
        "lat": 41.199,
        "lon": -91.487,
        "planting": "05-11",
        "n": 488,
        "sd": 24.7,
        "blocks": {75: 158.7, 150: 174.3, 225: 162.2},
        "dates": ["07-10", "07-20", "08-02", "09-13", "10-01", "10-09"],
        "ndvi": [0.86, 0.84, 0.79, 0.43, 0.25, 0.25],
        "rho": [0.30, 0.33, 0.40, 0.31, 0.12, -0.11],
    },
    "Lincoln": {
        "lat": 40.852,
        "lon": -96.615,
        "planting": "05-22",
        "n": 504,
        "sd": 24.9,
        "blocks": {75: 43.0, 150: 53.2, 225: 27.5},
        "dates": ["07-18", "08-06", "09-03", "09-11", "09-19", "09-27"],
        "ndvi": [0.79, 0.63, 0.42, 0.38, 0.35, 0.35],
        "rho": [0.47, 0.57, -0.33, -0.47, -0.52, -0.52],
    },
}
# A later season at one site, to exercise the 2022 -> 2023 path (entirely invented).
SEASON_2023 = {
    "Ames": {
        "planting": "05-08",
        "n": 300,
        "sd": 28.0,
        "blocks": {75: 168.0, 150: 181.0, 250: 186.0},
        "dates": ["07-05", "07-19", "08-04", "08-22", "09-08", "09-26"],
        "ndvi": [0.74, 0.82, 0.83, 0.80, 0.71, 0.48],
        "rho": [0.25, 0.42, 0.55, 0.50, 0.33, 0.12],
    }
}
N_HYBRIDS = 84
M_PER_DEG = 111_320.0
ROWS_PER_RANGE = 10


def _plots_for(site, year, spec, hybrid_effect, rng, scale: float):
    n = max(12, int(spec["n"] * scale))
    rates = list(spec["blocks"])
    block_of = np.sort(np.arange(n) % len(rates))
    rows = []
    for b, rate in enumerate(rates):
        members = np.nonzero(block_of == b)[0]
        for j, _ in enumerate(members):
            rng_, row = divmod(j, ROWS_PER_RANGE)
            rows.append(
                {
                    "block": b,
                    "nitrogen_lb_ac": float(rate),
                    "range": rng_ + 1,
                    "row": row + 1,
                    "x_m": b * 90.0 + row * 5.5,
                    "y_m": rng_ * 7.0,
                }
            )
    p = pd.DataFrame(rows)
    p["site_id"], p["year"] = site, year
    p["plot_id"] = [f"{site}-{year}-{r.block}-{r.range}-{r.row}" for r in p.itertuples()]
    p["field_id"] = [f"{site}-{year}-block{b}" for b in p["block"]]
    p["genotype"] = [f"H{int(h):03d}" for h in rng.integers(0, N_HYBRIDS, len(p))]
    p["genotype"] = p["genotype"].where(rng.random(len(p)) > 0.03)  # a few unrecorded
    p["planting_date"] = pd.Timestamp(f"{year}-{spec['planting']}")
    p["irrigated"] = False
    lat0 = spec.get("lat", SITES[site]["lat"])
    lon0 = spec.get("lon", SITES[site]["lon"])
    p["latitude"] = lat0 + p["y_m"] / M_PER_DEG
    p["longitude"] = lon0 + p["x_m"] / (M_PER_DEG * np.cos(np.radians(lat0)))

    g = p["genotype"].map(lambda h: 0.0 if pd.isna(h) else hybrid_effect[int(h[1:])]).to_numpy()
    gxe = rng.normal(0, 5, N_HYBRIDS)
    g = g + p["genotype"].map(lambda h: 0.0 if pd.isna(h) else gxe[int(h[1:])]).to_numpy()
    block_mean = p["nitrogen_lb_ac"].map(spec["blocks"]).to_numpy()
    phase = rng.uniform(0, 2 * np.pi, 4)
    spatial = (
        np.sin(p["x_m"] / 60 + phase[0])
        + np.cos(p["y_m"] / 45 + phase[1])
        + 0.5 * np.sin((p["x_m"] + p["y_m"]) / 30 + phase[2])
    ).to_numpy()
    spatial = 8 * spatial / spatial.std()
    signal = block_mean + g + spatial
    noise_sd = np.sqrt(max(spec["sd"] ** 2 - np.var(signal - block_mean.mean()), 120.0))
    p["final_yield"] = np.clip(signal + rng.normal(0, noise_sd, len(p)), 1.0, None)
    p["_signal"] = signal
    return p


def _passes(p, spec, year, rng):
    s = p["_signal"].to_numpy()
    z = (s - s.mean()) / s.std()
    persistent = rng.normal(0, 1, len(p))
    rows = []
    for k, (date, median, rho) in enumerate(
        zip(spec["dates"], spec["ndvi"], spec["rho"], strict=True), 1
    ):
        e = 0.6 * persistent + 0.8 * rng.normal(0, 1, len(p))
        ndvi = median + 0.045 * (rho * z + np.sqrt(1 - rho**2) * e)
        rows.append(
            pd.DataFrame(
                {
                    "plot_id": p["plot_id"],
                    "tp": k,
                    "date": pd.Timestamp(f"{year}-{date}"),
                    "ndvi": ndvi,
                    "ndre": 0.47 * ndvi - 0.02 + rng.normal(0, 0.012, len(p)),
                    "gndvi": 0.85 * ndvi + 0.06 + rng.normal(0, 0.015, len(p)),
                    "evi": 1.05 * ndvi - 0.10 + rng.normal(0, 0.03, len(p)),
                    "nir": 0.22 + 0.28 * ndvi + rng.normal(0, 0.02, len(p)),
                }
            )
        )
    obs = pd.concat(rows, ignore_index=True)
    missing = rng.random(len(obs)) < 0.01  # a few clouded or unsegmented passes
    return obs[~missing]


def make_frames(
    seed: int = 7, scale: float = 1.0, with_2023: bool = False
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(plots, per-pass observations, acquisitions) for the fixture."""
    rng = np.random.default_rng(seed)
    hybrid_effect = rng.normal(0, 11, N_HYBRIDS)
    seasons = [(2022, SITES)] + ([(2023, SEASON_2023)] if with_2023 else [])
    plots, obs, acq = [], [], []
    for year, sites in seasons:
        for site, spec in sites.items():
            p = _plots_for(site, year, spec, hybrid_effect, rng, scale)
            plots.append(p)
            obs.append(_passes(p, spec, year, rng))
            acq += [
                {"site_id": site, "year": year, "tp": k, "date": f"{year}-{d}"}
                for k, d in enumerate(spec["dates"], 1)
            ]
    plots = pd.concat(plots, ignore_index=True)
    unimaged = plots["plot_id"].sample(frac=0.01, random_state=seed)
    observations = pd.concat(obs, ignore_index=True)
    observations = observations[~observations["plot_id"].isin(unimaged)]
    keep = [
        "plot_id", "field_id", "site_id", "year", "planting_date", "latitude", "longitude",
        "genotype", "nitrogen_lb_ac", "irrigated", "final_yield", "range", "row",
    ]  # fmt: skip
    return plots[keep], observations.reset_index(drop=True), pd.DataFrame(acq)


def synthetic_data(seed: int = 7, scale: float = 1.0, with_2023: bool = False) -> ExperimentData:
    plots, observations, acquisitions = make_frames(seed, scale, with_2023)
    return from_frames(
        "SYNTHETIC-fixture",
        plots,
        tp_observations=observations,
        acquisitions=acquisitions,
        value_columns=["ndvi", "ndre", "gndvi", "evi", "nir"],
        synthetic=True,
        provenance={
            "dataset": "SYNTHETIC-fixture",
            "warning": "Random data shaped like the practice dataset. Not a result.",
            "seed": seed,
            "scale": scale,
            "with_2023": with_2023,
        },
    )
