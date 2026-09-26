# Historical weather outlook: method, data and results

SoilSignal's weather uncertainty component. It answers: *at this maize trial site, on this
date, what did the next 30, 60, 90 days (or the rest of the season) bring in past seasons,
and how often was that favorable, typical or adverse for maize?* It also hands the yield
model every one of those historical weather trajectories, so the yield model can say what
it would predict under each.

It is a **historical analog outlook**, not a meteorological forecast. Historical
observations cannot say "there is a 63% chance of rain next June"; they can say how often
comparable seasons were followed by a given kind of weather.

| | |
|---|---|
| Engine (shared with the API) | `backend/app/weather_outlook/` |
| Research tooling (data, QC, backtest, reports) | `ml/soilsignal_ml/weather_outlook/`, CLI `python -m soilsignal_ml.weather_outlook` (or `ml/weather_outlook.py`) |
| Settings, fixed before the backtest | `ml/configs/weather_outlook.yaml` |
| Published weather libraries | `backend/data/weather_history/{supplied,long}/` (`daily.csv.gz` + `manifest.json`) |
| Data QC report | `ml/experiments/weather_outlook/data_qc.md` |
| Backtests | `ml/experiments/weather_outlook/{supplied,long}/backtest.md`, `summary.csv`, `cases.csv`, `figures/` |
| API | `GET /api/weather-outlook?site=Ames&asOfDate=2023-06-01&horizonDays=60` |

## 1. Results in brief

- **Data.** The challenge weather file is clean and complete, but it is IEM's *computed*
  daily summary: from 2020 its daily maxima run about 0.4 C below NOAA's official record
  for the same airports and its minima about 0.5 C above, so it under-counts 95 F days
  (Scottsbluff 2020: 38 vs 48; Lincoln 2022: 25 vs 28). This also affects the heat
  features SoilSignal's yield models are trained on. Solar radiation, ET and soil moisture
  exist only at Crawfordsville.
- **Long history.** 27-31 quality-checked seasons per site (1994/1998-2025), from NOAA
  GHCN-Daily for the same four airport stations and, for Crawfordsville, one documented
  proxy station (Washington, IA, 21 km). No station is spliced to another.
- **Skill.** Leave-one-season-out over 148 site-seasons x 8 dates x 4 horizons:
  - At the four **rainfed** sites, weighting seasons by similarity to the season so far
    was slightly but consistently *worse* than weighting them equally: RPSS -0.018 (90%
    interval over seasons -0.028 to -0.008). Rainfall over the next 1-3 months is not
    predictable from how the season has gone so far at these stations.
  - At **Scottsbluff** (irrigated, so scored on heat) analogs beat equal weights at every
    horizon: RPSS +0.095 (+0.044 to +0.140), CRPSS for degree days above 29 C +0.078
    (+0.037 to +0.112). Warm-season heat persists on the High Plains.
  - With only the six supplied seasons, analogs were clearly worse (RPSS -0.16): five
    analogs are too few to weight.
- **What the product therefore does.** Scottsbluff uses analog weights; the rainfed sites
  and the six-season library weigh every season equally, which the outlook states
  (`weighting` in the contract). The probabilities there are the climatological terciles,
  honestly labelled. The component's lasting value is the ensemble of real weather
  trajectories for the yield model (section 7), not predictive skill over climatology.

## 2. Data assessment

Details and every table: `ml/experiments/weather_outlook/data_qc.md`.

**Supplied file** (`weather_daily_2018-02-01_2023-11-30.csv`, 10,645 rows): 5 sites x
2,129 days, one station per site, no duplicate site-days, `tmax_c`/`tmin_c` complete,
`precip_mm` missing 25 days (1 in any April-October), 58 rows `qc_status = partial`
(humidity/wind gaps). The file carries every source's raw columns next to the normalized
ones; only the normalized `tmax_c`, `tmin_c`, `precip_mm` are used.

- `srad_mj`, `et_mm`, soil temperature and moisture: Crawfordsville (ISU Soil Moisture
  Network) only, so they are not usable for a five-site method.
- `avg_rh`, `avg_wind_speed_mps`: ~99% complete, but absent from NOAA's long records and
  not used by SoilSignal's weather features, so not used.
- Re-downloading from IEM reproduces the file exactly (0 differences), so it is IEM's
  computed summary. Against NOAA GHCN-Daily for the same airports, 2018-2019 agree to
  0.05 C, but 2020-2023 (and IEM's pre-2009 years) differ by -0.4 C (tmax) / +0.5 C (tmin).
  IEM's summaries also record zeros where the gauge was out (LNK 1995: 13 mm for April-
  October vs 491 mm official). **The long library uses NOAA's official record.** The supplied
  library is kept exactly as delivered.

## 3. Long-history library

Target: 20-30 complete seasons per site, the same stations where possible.

| Site | Station | Same as supplied | Seasons kept | Left out |
|---|---|---|---|---|
| Ames | Ames Municipal Airport (AMW), GHCND:USW00094989 | yes | 27 (1998-2025) | 1994-97 (not yet reporting), 2008 (precip 96% complete) |
| Crawfordsville | Washington, IA NWS COOP, GHCND:USC00138688, 21 km | **no (proxy)** | 31 (1994-2025) | 2011 (precip 75%) |
| Lincoln | Lincoln Airport (LNK), GHCND:USW00014939 | yes | 31 (1994-2025) | 2014 (temperatures disagree with both neighbours) |
| MOValley | Tekamah Airport (TQE), GHCND:USW00094978 | yes | 28 (1998-2025) | 1994-97 (not yet reporting) |
| Scottsbluff | Scottsbluff Heilig Field (BFF), GHCND:USW00024028 | yes | 31 (1994-2025) | 2004 (tmin disagrees with the one neighbour able to check it) |

**Crawfordsville.** The on-site station (CRFI4, 0.7 km) starts December 2013: ten seasons.
Candidates within 30 km were compared with CRFI4 over 2014-2026:

| Station | km | Complete seasons 1994-2023 | Season rain vs CRFI4 (r) | Note |
|---|---|---|---|---|
| Columbus Junction | 14 | 10 | 0.99 but ratio 0.33 | gauge problems |
| **Washington** | 21 | 26 (31 after gap handling) | 0.90 | 07:00 observer |
| Mount Pleasant | 27 | 24 | 0.77 | station change ~2021 |

Washington reports each morning at 07:00, so the value dated D covers 07:00 D-1 to 07:00 D.
Assigning every value to D-1 raises the daily correlation with CRFI4 from 0.82 to 0.98
(tmax), 0.29 to 0.66 (rain) and 0.94 to 0.95 (tmin). After alignment Washington is 0.70 C
cooler by day and 0.95 C cooler by night than the field station, with 8% more season rain
(season totals r = 0.87). The library uses Washington for **every** Crawfordsville season,
including the current one, so analog matching compares like with like. When a plot's own
weather is supplied (the yield-model path), trajectories are shifted by the measured
monthly temperature difference so they continue the field station's record; rain is not
adjusted. Using CRFI4 alone (ten seasons) remains possible by publishing a library from it.

**Quality control** (`history.qc_seasons`): one station per site for every season.

1. A season needs >= 97% of days with tmax, tmin and rain over 1 April-30 November.
2. Temperature gaps of 1-2 days are interpolated within the station and flagged per day
   (`temp_filled`); rain is never filled. (Without this, the feature code counts a day with
   a missing temperature as 0 GDD.)
3. Each season is compared with 1-3 nearby stations: rain ratio and mean temperature
   difference against the pair's *usual* value (median over the 11 nearest seasons). A
   season is left out only when **every** neighbour able to check it disagrees (rain by
   more than 1.5x, temperature by more than 1 C). Neighbours never supply data.

The first QC pass used a single neighbour, a full-period median and a 1.35x rain
tolerance. It flagged Crawfordsville 2024-25 and Lincoln 2003, which on inspection were
station changes at the *neighbours* (Mount Pleasant's minima jump ~1.4 C around 2021;
Crete's offset steps ~1.3 C in 2013), and dropped nine Crawfordsville seasons for
scattered one-day temperature gaps. The rules above replaced it before any backtest was
run; no rule was changed after seeing outlook results.

## 4. Method

**Season so far (descriptors).** From 1 April (spring rain recharges the root zone, so
it counts) through the as-of date, with `app.features.weather.weather_features`, the same
function the yield models use: growing degree days, rain to date, rain in the last 30
days, mean temperature over the last 30 days (plus heat days, dry spells, warm nights and
root-zone depletion, reported but not matched on). No GDD, heat or dry-spell formula is
redefined; tests check the outlook's numbers equal the feature pipeline's.

**Site- and date-specific standardization.** Each descriptor is standardized against the
same site's other seasons on the same month-day, with the median and interquartile range
(MAD if the IQR is 0), so 20 mm at Scottsbluff is compared with Scottsbluff Junes, and one
extreme season cannot set the scale. Descriptors that do not vary (no heat days anywhere
yet) drop out.

**Analog weights.** Distance = root-mean-square robust z difference; weight
`exp(-d^2 / 2h^2)` with h = 1. If the effective sample size `(sum w)^2 / sum w^2` falls below
40% of the seasons, h widens until it does not, so a few close analogs never carry the
outlook. Before 21 days of season have been observed, every season weighs the same. Where
the backtest found no gain (section 6), every season weighs the same.

**Trajectories.** For each historical season, the real weather from the day after the
as-of month-day through the horizon, re-dated into the current season. The outlook's own
season is never a candidate. Horizons: any number of days (30/60/90) or `season` (through
15 October, the last model cutoff), ending no later than 30 November.

**Weather-only outcomes (Layer 1).** Per trajectory: rain, GDD, 95 F days, degree days
above 29 C, 70 F nights, longest dry spell, 20 mm days, crop water deficit (from planting,
with SoilSignal's Hargreaves ET and Kc), mean temperature; for `season`, the silking and
grain-fill windows of the season so far plus that trajectory. Reported as weighted mean,
20th/50th/80th percentiles, the climatological median, and below/near/above-normal
tercile probabilities; plus the chance of any 95 F day and of any 20 mm day.

**Favorable / typical / adverse.** Categories are terciles of a score over the
**unweighted** historical trajectories (fixed cut points for that site, date and horizon);
weights then move probability between those fixed categories. Scores:

- **Intended: the yield model.** `couple_yield` runs every trajectory through the yield
  model with the plot's imagery, hybrid, nitrogen, irrigation and planting fixed.
- **Provisional until then**, using published relationships with no fitted or hand-set
  weights between variables:
  - rainfed: relative yield from water supply, FAO-33 (Doorenbos & Kassam 1979): for each
    growth period in the horizon, 1 - Ky (1 - ETa/ETc), multiplied; Ky 0.4 vegetative,
    1.5 flowering (silking +/-14 days), 0.5 yield formation, 0.2 ripening. ETa from an
    FAO-56 root-zone water balance (capacity = SSURGO available water storage at the site,
    p = 0.55, full on 1 April). Rain beyond root-zone capacity drains, so wetter is not
    automatically better; exact ties (no stress) are ordered by soil water left.
  - irrigated (Scottsbluff): degree days above 29 C weighted by the same growth-period Ky.

  The contract says which scorer defined the categories (`categoryBasis`), and flags the
  provisional ones. If every trajectory scores the same (e.g. a yield model that ignores
  weather), no categories are reported rather than forced thirds.

**Uncertainty.** Whole percentages; the number of seasons and the effective number after
weighting; an 80% bootstrap interval per category (500 resamples of the historical
seasons, re-running the standardization, weights and cut points each time). Fewer than
20 seasons: labelled *Exploratory, based on N historical seasons*.

**No leakage.** The current season is read only through the as-of date; the outlook's
own season is excluded from the analogs; standardization uses the analog seasons only.
Tests change the current season's weather after the as-of date (in the library and in
supplied plot weather) and check the outlook is unchanged, and, as a control, that
changing it before the as-of date does change the analogs.

## 5. Output contract

`app/weather_outlook/contract.py`, `contractVersion` 1. Main fields:

```json
{
  "site": "Scottsbluff", "asOfDate": "2023-06-15", "horizonDays": 60,
  "method": "historical_analogs", "weighting": "Seasons that resembled this one so far weigh more.",
  "historicalSeasons": 30, "effectiveSampleSize": 25.0, "exploratory": false,
  "reliability": "Based on 30 historical seasons",
  "categoryBasis": {"scorer": "stage_weighted_heat", "provisional": true, "available": true},
  "probabilities": {"adverse": 0.23, "typical": 0.39, "favorable": 0.38},
  "probabilityIntervals": {"adverse": [0.15, 0.29], "typical": [0.30, 0.45], "favorable": [0.32, 0.47]},
  "climatology": {"adverse": 0.34, "typical": 0.33, "favorable": 0.33},
  "weatherSummary": {"killingDegreeDays29c": {"mean": 52.4, "p20": 37.5, "median": 49.4, "p80": 66.9,
                     "climatologyMedian": 53.1, "terciles": {"below": 0.38, "near": 0.38, "above": 0.24}}},
  "representativeScenarios": {"adverse": {"season": 2000}, "typical": {"season": 2025}, "favorable": {"season": 2018}},
  "analogs": [{"season": 2018, "weight": 0.07, "distance": 0.4, "category": "favorable"}]
}
```

Full examples: `ml/experiments/weather_outlook/examples/`. The trajectories themselves
(one row per trajectory day: `source_season`, `weight`, `category`, `date`, `tmax_c`,
`tmin_c`, `precip_mm`, `gdd_f`) come from `trajectories_frame()`, written as Parquet by
`python -m soilsignal_ml.weather_outlook outlook ... --parquet out.parquet`.

## 6. Backtest

Leave one season out: for every site, QC-passed season, as-of date (1 May ... 15 August,
twice a month) and horizon (30, 60, 90 days, season), the outlook is built from the other
seasons and scored against what that season did. The reference is the same outlook with
equal weights (climatology), so skill is the analog weighting's alone. Scores: ranked
probability score (RPS/RPSS) and Brier score over the three ordered categories, accuracy of
the most likely category, reliability, and CRPS for continuous outcomes. Intervals resample
whole site-seasons (cases within a season share its weather).

| Library, sites | Cases | Mean ESS | RPSS (90% interval) | Accuracy analog / equal |
|---|---|---|---|---|
| supplied, all (5 analogs) | 960 | 3.1 | -0.160 (-0.232, -0.088) | 36.7% / 34.2% |
| long, all | 4,736 | 21.6 | +0.006 (-0.008, +0.021) | 36.4% / 33.3% |
| long, rainfed (Ames, Crawfordsville, Lincoln, MOValley) | 3,744 | 21.2 | -0.018 (-0.028, -0.008) | 33.5% / 33.3% |
| long, Scottsbluff (irrigated, heat) | 992 | 23.2 | +0.095 (+0.044, +0.140) | 47.3% / 33.0% |

By horizon (long, all sites) RPSS is +0.004 to +0.007 with intervals spanning zero; by
as-of date it is slightly positive through July and slightly negative in August. For
continuous outcomes at Scottsbluff, CRPSS is +0.078 for degree days above 29 C and +0.080
for 95 F days; at the rainfed sites every CRPSS is within +/-0.015 of zero.

Reliability: the ESS floor keeps analog probabilities close to one third (86% of category
probabilities fall in 0.2-0.4), where they are well calibrated; the few above 0.4 are
somewhat overconfident (0.44 forecast, 0.39 observed).

The per-site weighting decision (`analog_weighting` in the config) was made from this
backtest, so the Scottsbluff estimate is from the same data that selected it: treat +0.095
as optimistic, though its interval is well clear of zero. Choosing equal weights at the
rainfed sites claims no skill, so it carries no such bias. With more seasons, or a
weather-sensitive yield model as the scorer, re-run the backtest and revisit the setting.

## 7. The yield model's interface (Layer 2)

```python
from datetime import date
from app.weather_outlook.history import WeatherLibrary
from app.weather_outlook.scenarios import WeatherOutlook, couple_yield
from app.weather_outlook.coupling import artifact_predictor

outlook = WeatherOutlook(WeatherLibrary(path_to_library)).generate(
    "Crawfordsville", date(2022, 7, 1), "season",
    planting=inputs.planting_date, current_weather=inputs.weather)  # the plot's own weather

for trajectory in outlook.trajectories:          # one per historical season
    trajectory.season, trajectory.weight          # where it comes from, its analog weight
    season = outlook.season_weather(trajectory)   # observed through as-of, then this trajectory
    # -> list[DailyWeather], exactly what FieldInputs.weather holds

coupled = couple_yield(outlook, predict)          # predict(season_weather) -> bu/ac
coupled.yields, coupled.distribution(), coupled.by_category()
```

`artifact_predictor(artifact, inputs, as_of, feature_date)` builds `predict` from any
exported SoilSignal model: imagery after the as-of date is dropped, the weather is
replaced, features are built with `build_features` at the model's own cutoff. The
imagery team needs nothing from the outlook's statistics; they supply a model whose
features include weather after the as-of date.

Demonstration on the practice bundle (`yield_coupling_demo_2022-05-31.json`, Crawfordsville
plot, as of 31 May 2022): the June 30 model uses 25 weather features and gives 110-138
bu/ac across the 31 trajectories (adverse / typical / favorable means 112 / 124 / 133). The
May 31 model sees no weather after its cutoff, and the July-October models use no weather
features at all, so under them every trajectory gives the same yield and the outlook
reports that categories cannot be formed. The practice models' validation R^2 is negative;
this shows the plumbing, not a usable yield range. **For Layer 2 to define favorable and
adverse, the ML team's end-of-season model needs weather features after the as-of date.**

## 8. Limitations

- Not a forecast: no atmospheric state, sea-surface temperatures or ENSO. NOAA CPC
  monthly/seasonal outlooks or NMME ensembles could condition the analog weights later.
- Climate trend: every other season is a candidate, including later ones; a warming trend
  is not modelled. A past-only library is the conservative alternative for a trend study.
- The provisional scorer is not a yield model: no direct heat damage at pollination in
  the rainfed score, no waterlogging, fixed GDD stage milestones and reference planting
  dates (the 2022 trial dates), a single-layer bucket that starts full on 1 April.
- Crawfordsville trajectories come from a proxy station (documented, bias measured).
- 2024-2025 seasons are included (they postdate the challenge data); the challenge's own
  seasons (2022, 2023) are always left out of their own outlook.
- Tercile categories need at least a few seasons per third; with the six supplied seasons,
  probabilities move in steps of 20%.

## 9. Reproduce

```bash
cd ml
uv run --project ../backend --group ml python -m soilsignal_ml.weather_outlook history      # download, QC, publish
uv run --project ../backend --group ml python -m soilsignal_ml.weather_outlook backtest --library long
uv run --project ../backend --group ml python -m soilsignal_ml.weather_outlook backtest --library supplied
uv run --project ../backend --group ml python -m soilsignal_ml.weather_outlook outlook --site Ames --as-of 2023-06-01 --horizon 60
uv run --project ../backend --group ml python -m soilsignal_ml.weather_outlook yield --as-of 2022-05-31
```

The supplied file goes in `ml/data/raw/weather/` (from the team Drive folder); NOAA and IEM
downloads are cached there. `history` fetches through two days ago; pass `--end` to pin it.
