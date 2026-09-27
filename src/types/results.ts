/**
 * The frozen final results (GET /api/results, GET /api/results/plots).
 * Mirrors backend/app/results.py. `pending` until the ML team publishes
 * artifacts/final_results.json; nothing is estimated in its place.
 */

export interface ResultsModel {
  name: string; // e.g. "Random Forest"
  validation: string; // e.g. "leave-one-site-out"
  description?: string | null;
  features?: string[] | null;
}

export interface IntervalInfo {
  level?: number | null; // nominal, e.g. 0.9
  coverage?: number | null; // share of validation yields inside the range
  method?: string | null;
}

export interface StagePerformance {
  dap: number; // days after planting
  stage?: string | null; // key matching ResultForecastPoint.stage, e.g. "TP3"
  label?: string | null; // for people, e.g. "TP3 · site DAP 79–104"
  mae?: number | null; // bu/ac
  rmse?: number | null;
  r2?: number | null;
  n?: number | null;
}

export interface ResultForecastPoint {
  date: string;
  dap: number;
  stage?: string | null; // the validation stage, e.g. "TP3"
  yield: number;
  lower?: number | null;
  upper?: number | null;
}

export interface SiteForecast {
  site: string;
  season: number;
  plots?: number | null;
  forecasts: ResultForecastPoint[];
}

export interface PlotUav {
  dap?: number | null;
  satelliteOnly: number;
  satellitePlusUav: number;
}

export interface ResultPlot {
  plotId: string;
  site: string;
  season: number;
  hybrid?: string | null;
  nitrogenLbAc?: number | null;
  plantingDate?: string | null;
  irrigated?: boolean | null;
  forecasts: ResultForecastPoint[];
  uav?: PlotUav | null;
  featured?: boolean; // the plot the dashboard opens on at its site
}

export interface MaturityEstimate {
  site: string;
  season: number;
  plotId?: string | null; // null: the whole site
  asOf: string;
  gddSincePlanting?: number | null;
  gddToMaturity?: number | null;
  windowStart?: string | null;
  windowEnd?: string | null;
  method?: string | null;
}

export interface ValidationMetrics {
  r2?: number | null;
  mae?: number | null; // bu/ac
  rmse?: number | null;
  coverage?: number | null; // share of validation yields inside the range
  medianIntervalWidth?: number | null; // bu/ac, upper - lower
  n?: number | null;
}

export interface SiteStage extends ValidationMetrics {
  stage: string; // matches ResultForecastPoint.stage
  dap: number; // the site's typical days after planting at this stage
  dapMin?: number | null;
  dapMax?: number | null;
}

/** One site's own validation: before any imagery, then each satellite stage. */
export interface SitePerformance {
  site: string;
  season: number;
  plots?: number | null;
  folds?: number | null;
  preseason?: ValidationMetrics | null; // field records only
  stages: SiteStage[];
}

export interface UavVariant {
  mae: number;
  rmse?: number | null;
  r2?: number | null;
}

/** Numbers are shown only when `matched`: same plots, dates, split and framework. */
export interface UavComparison {
  matched: boolean;
  sites: string[];
  plots?: number | null;
  dap?: number | null;
  validation?: string | null;
  framework?: string | null;
  satelliteOnly: UavVariant;
  satellitePlusUav: UavVariant;
  note?: string | null;
}

export interface PlotCount {
  site: string;
  season: number;
  plots: number;
  observations: number; // dated forecasts across those plots
}

export interface FinalResults {
  status: 'pending' | 'ready';
  contractVersion: number;
  resultsVersion?: string | null;
  generatedAt?: string | null;
  datasetLabel?: string | null;
  unit: string;
  model?: ResultsModel | null;
  interval?: IntervalInfo | null;
  performance: StagePerformance[];
  earliestUsefulDap?: number | null;
  earliestUsefulRule?: string | null;
  sites: SiteForecast[];
  plotCounts: PlotCount[];
  sitePerformance: SitePerformance[];
  maturity: MaturityEstimate[];
  uav?: UavComparison | null;
}
