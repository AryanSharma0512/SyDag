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
  label?: string | null; // e.g. "TP1-TP3"
  mae?: number | null; // bu/ac
  rmse?: number | null;
  r2?: number | null;
  n?: number | null;
}

export interface ResultForecastPoint {
  date: string;
  dap: number;
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
  maturity: MaturityEstimate[];
  uav?: UavComparison | null;
}
