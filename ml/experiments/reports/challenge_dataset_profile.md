# Dataset profile: challenge2022

SyDAg26 IoT4Ag hackathon challenge data (organizers' shared folder); the plots, images and README match Shrestha N., Powadi A., Davis J., et al. (2024), doi:10.5061/dryad.905qftttm.

- 1026 plots with imagery, 960 with a harvested yield; 1960 plot images on 17 dates; 84 hybrids.
- Data checks: all passed.
- Plot key: {year}-{site}-{experiment}-{range}-{row} (ml/data/challenge).
- Acquisition dates from DateofCollection.xlsx; TP numbers differ by site.
- Satellite indices: mean over the plot's pixels of per-pixel indices, reflectance = DN x 1e-4.
- Fill plots without a planting date take their site + experiment's date.

## Sites

| Site_id | County | State | Latitude | Longitude | Weather_station | Station_distance_km |
|---|---|---|---|---|---|---|
| Ames | Boone County | IA | 42.015 | -93.732 | Ames 8 Wsw, IA | 3.500 |
| Crawfordsville | Washington County | IA | 41.199 | -91.487 | Columbus Junction, IA | 13.800 |
| Lincoln | Lancaster County | NE | 40.852 | -96.615 | Lincoln 8 Ene, NE | 4.200 |

## Yield (bu/ac at 15.5% moisture)

| Site | Irrigated | Plots | Hybrids | Mean | SD | Min | Max |
|---|---|---|---|---|---|---|---|
| Ames | False | 233 | 84 | 121.4 | 29.3 | 44.0 | 207.1 |
| Crawfordsville | False | 312 | 84 | 164.9 | 23.6 | 93.8 | 243.9 |
| Lincoln | False | 415 | 84 | 41.3 | 25.4 | 1.7 | 144.9 |

Between-site differences dwarf within-site ones: Lincoln (rainfed, 2022 drought) averages about a quarter of Crawfordsville. Leave-one-site-out validation is hard for exactly this reason.

### Mean yield by nitrogen rate

| Site | 75 lb N | 150 lb N | 225 lb N | 250 lb N |
|---|---|---|---|---|
| Ames | – | 116.1 | – | 123.6 |
| Crawfordsville | 159.6 | 175.3 | 160.3 | – |
| Lincoln | 43.3 | 54.4 | 27.1 | – |

## Canopy: median NDVI by image

| Site | Image dates | Image 1 | Image 2 | Image 3 | Image 4 | Image 5 | Image 6 |
|---|---|---|---|---|---|---|---|
| Ames | Jul 15, Jul 23, Aug 10, Aug 31, Sep 11, Sep 24 | 0.77 | 0.81 | 0.79 | 0.78 | 0.74 | 0.53 |
| Crawfordsville | Jul 10, Jul 20, Aug 02, Sep 13, Oct 01, Oct 09 | 0.86 | 0.84 | 0.79 | 0.44 | 0.25 | 0.24 |
| Lincoln | Jul 18, Aug 06, Sep 03, Sep 11, Sep 19, Sep 27 | 0.79 | 0.63 | 0.42 | 0.39 | 0.34 | 0.35 |

### Correlation of NDVI with final yield, within each site

| Site | Image 1 | Image 2 | Image 3 | Image 4 | Image 5 | Image 6 |
|---|---|---|---|---|---|---|
| Ames | -0.00 | 0.36 | 0.65 | 0.69 | 0.60 | 0.29 |
| Crawfordsville | 0.19 | 0.17 | 0.38 | 0.34 | 0.04 | -0.31 |
| Lincoln | 0.46 | 0.64 | -0.22 | -0.55 | -0.52 | -0.54 |

## Weather, planting to Sep 30 (NOAA GHCN-Daily)

| Site | Planted | Rain, planting-Sep 30 (mm) | GDD, planting-Sep 30 | Days ≥ 95 °F | Nights ≥ 70 °F | Filled from other stations (days) |
|---|---|---|---|---|---|---|
| Ames | 2022-05-22 | 527 | 2,855 | 3 | 21 | 0 |
| Crawfordsville | 2022-05-11 | 369 | 2,956 | 2 | 11 | 3 |
| Lincoln | 2022-05-22 | 305 | 2,886 | 15 | 18 | 1 |

## Growth stage check

Features place silking at 1,300 GDD after planting (ISU PMR 1009). Two sites recorded anthesis:

| Site | Plots | Days to anthesis (median) | GDD to anthesis, NOAA weather (median) | GDD to anthesis, as recorded (median) | Feature milestone (GDD) |
|---|---|---|---|---|---|
| Lincoln | 413 | 59 | 1,339 | 1,346 | 1,300 |

## Soil (SSURGO dominant component at each plot)

| Site | Series | Drainage | Available water, 100 cm (cm) | Organic matter (%) | pH |
|---|---|---|---|---|---|
| Ames | Nicollet (256) | Somewhat poorly drained | 19.1 | 6.0 | 6.2 |
| Crawfordsville | Taintor (230), Kalona (55), Mahaska (47) | Poorly drained | 19.3 | 4.2 | 6.4 |
| Lincoln | Aksarben (347), Crete (74), Butler (17) | Well drained | 15.7 | 3.4 | 5.7 |

## County corn yield history (USDA NASS, bu/ac)

| Year |
|---|

## Missing values

| Column | Missing (plots) |
|---|---|
| final_yield | 66 |
| genotype | 66 |
| planting_date | 0 |
| latitude | 0 |
| stand_count | 481 |
| days_to_anthesis | 613 |

Stand counts and anthesis dates exist at only some sites and have no reliable measurement date, so they are profiled here but never used as features.
