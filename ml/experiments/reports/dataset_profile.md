# Dataset profile: shrestha2024

Shrestha N., Powadi A., Davis J., et al. (2024). Crop performance, aerial, and satellite data from multistate maize yield trials. Dryad/Zenodo, doi:10.5061/dryad.905qftttm. CC0 1.0.

- 2275 plots with imagery, 2131 with a harvested yield; 13650 plot images on 25 dates; 84 hybrids.
- Data checks: all passed.
- North Platte, NE is excluded by the authors (plot segmentation issues).
- Only satellite imagery is used; the UAV images are RGB only.
- Plot coordinates are the centre of each plot's georeferenced image.
- 16 ground-truth plots have no satellite image and are dropped.

## Sites

| Site_id | County | State | Latitude | Longitude | Weather_station | Station_distance_km |
|---|---|---|---|---|---|---|
| Ames | Boone County | IA | 42.014 | -93.734 | Ames 8 Wsw, IA | 3.400 |
| Crawfordsville | Washington County | IA | 41.199 | -91.487 | Columbus Junction, IA | 13.800 |
| Lincoln | Lancaster County | NE | 40.852 | -96.615 | Lincoln 8 Ene, NE | 4.200 |
| MOValley | Harrison County | IA | 41.671 | -95.942 | Logan 1 Wnw, IA | 11.600 |
| Scottsbluff | Scotts Bluff County | NE | 41.950 | -103.703 | Scottsbluff 1 E, NE | 10.800 |

## Yield (bu/ac at 15.5% moisture)

| Site | Irrigated | Plots | Hybrids | Mean | SD | Min | Max |
|---|---|---|---|---|---|---|---|
| Ames | False | 487 | 84 | 130.3 | 31.8 | 27.3 | 221.5 |
| Crawfordsville | False | 488 | 84 | 165.1 | 24.7 | 69.5 | 243.9 |
| Lincoln | False | 504 | 84 | 41.2 | 24.9 | 1.7 | 144.9 |
| MOValley | False | 163 | 84 | 152.5 | 24.3 | 89.6 | 214.1 |
| Scottsbluff | True | 489 | 84 | 143.4 | 34.2 | 49.7 | 229.2 |

Between-site differences dwarf within-site ones: Lincoln (rainfed, 2022 drought) averages about a quarter of Crawfordsville. Leave-one-site-out validation is hard for exactly this reason.

### Mean yield by nitrogen rate

| Site | 75 lb N | 150 lb N | 175 lb N | 225 lb N | 250 lb N |
|---|---|---|---|---|---|
| Ames | 145.2 | 122.1 | – | – | 123.6 |
| Crawfordsville | 158.7 | 174.3 | – | 162.2 | – |
| Lincoln | 43.0 | 53.2 | – | 27.5 | – |
| MOValley | – | – | 152.5 | – | – |
| Scottsbluff | 120.1 | 149.2 | – | 161.5 | – |

## Canopy: median NDVI by image

| Site | Image dates | Image 1 | Image 2 | Image 3 | Image 4 | Image 5 | Image 6 |
|---|---|---|---|---|---|---|---|
| Ames | Jul 15, Jul 23, Aug 10, Aug 31, Sep 11, Sep 24 | 0.78 | 0.81 | 0.79 | 0.78 | 0.74 | 0.52 |
| Crawfordsville | Jul 10, Jul 20, Aug 02, Sep 13, Oct 01, Oct 09 | 0.86 | 0.84 | 0.79 | 0.43 | 0.25 | 0.25 |
| Lincoln | Jul 18, Aug 06, Sep 03, Sep 11, Sep 19, Sep 27 | 0.79 | 0.63 | 0.42 | 0.38 | 0.35 | 0.35 |
| MOValley | Jul 13, Jul 21, Aug 08, Sep 03, Sep 11, Sep 19 | 0.84 | 0.82 | 0.78 | 0.45 | 0.36 | 0.30 |
| Scottsbluff | Jul 04, Jul 17, Aug 07, Aug 18, Sep 09, Sep 24 | 0.36 | 0.56 | 0.77 | 0.80 | 0.75 | 0.71 |

### Correlation of NDVI with final yield, within each site

| Site | Image 1 | Image 2 | Image 3 | Image 4 | Image 5 | Image 6 |
|---|---|---|---|---|---|---|
| Ames | 0.06 | 0.31 | 0.57 | 0.57 | 0.36 | 0.16 |
| Crawfordsville | 0.30 | 0.33 | 0.40 | 0.31 | 0.12 | -0.11 |
| Lincoln | 0.47 | 0.57 | -0.33 | -0.47 | -0.52 | -0.52 |
| MOValley | 0.31 | 0.44 | 0.65 | 0.46 | 0.33 | 0.11 |
| Scottsbluff | -0.13 | -0.03 | -0.08 | -0.12 | -0.16 | -0.21 |

## Weather, planting to Sep 30 (NOAA GHCN-Daily)

| Site | Planted | Rain, planting-Sep 30 (mm) | GDD, planting-Sep 30 | Days ≥ 95 °F | Nights ≥ 70 °F | Filled from other stations (days) |
|---|---|---|---|---|---|---|
| Ames | 2022-05-22 | 527 | 2,855 | 3 | 21 | 0 |
| Crawfordsville | 2022-05-11 | 326 | 2,954 | 2 | 11 | 3 |
| Lincoln | 2022-05-22 | 305 | 2,886 | 15 | 18 | 1 |
| MOValley | 2022-04-29 | 400 | 3,028 | 8 | 11 | 35 |
| Scottsbluff | 2022-05-19 | 106 | 2,629 | 32 | 4 | 0 |

## Growth stage check

Features place silking at 1,300 GDD after planting (ISU PMR 1009). Two sites recorded anthesis:

| Site | Plots | Days to anthesis (median) | GDD to anthesis, NOAA weather (median) | GDD to anthesis, as recorded (median) | Feature milestone (GDD) |
|---|---|---|---|---|---|
| Lincoln | 501 | 59 | 1,339 | 1,346 | 1,300 |
| Scottsbluff | 508 | 74 | 1,443 | 1,393 | 1,300 |

## Soil (SSURGO dominant component at each plot)

| Site | Series | Drainage | Available water, 100 cm (cm) | Organic matter (%) | pH |
|---|---|---|---|---|---|
| Ames | Nicollet (306), Canisteo (230) | Somewhat poorly drained | 18.5 | 6.4 | 6.8 |
| Crawfordsville | Taintor (352), Kalona (90), Mahaska (80) | Poorly drained | 19.3 | 4.3 | 6.4 |
| Lincoln | Aksarben (423), Crete (89), Butler (20) | Well drained | 15.7 | 3.4 | 5.7 |
| MOValley | Kennebec (176) | Moderately well drained | 21.4 | 4.8 | 6.1 |
| Scottsbluff | Tripp (404), Mitchell (105) | Well drained | 18.4 | 1.8 | 7.2 |

## County corn yield history (USDA NASS, bu/ac)

| Year | Ames | Crawfordsville | Lincoln | MOValley | Scottsbluff |
|---|---|---|---|---|---|
| 2013 | 154.2 | 159.0 | 146.0 | 177.1 | 153.5 |
| 2014 | 180.9 | 191.3 | 155.7 | 161.1 | 177.5 |
| 2015 | 192.3 | 195.0 | 157.2 | 189.5 | 165.3 |
| 2016 | 208.4 | 208.2 | 163.2 | 204.6 | 161.6 |
| 2017 | 192.4 | 220.4 | 165.5 | 193.2 | 183.3 |
| 2018 | 193.7 | 214.3 | 179.7 | 176.0 | 194.8 |
| 2019 | 194.8 | 178.9 | 158.2 | – | 151.1 |
| 2020 | 160.7 | 185.4 | 167.0 | 180.2 | 141.2 |
| 2021 | 208.4 | – | 181.2 | – | 184.9 |
| 2022 | 202.4 | 185.7 | 112.1 | 172.4 | 165.4 |

## Missing values

| Column | Missing (plots) |
|---|---|
| final_yield | 144 |
| genotype | 118 |
| planting_date | 0 |
| latitude | 0 |
| stand_count | 1136 |
| days_to_anthesis | 1266 |

Stand counts and anthesis dates exist at only some sites and have no reliable measurement date, so they are profiled here but never used as features.
