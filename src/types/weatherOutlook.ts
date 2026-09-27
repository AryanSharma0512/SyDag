/**
 * Historical weather outlook, as the website uses it. Built by
 * src/services/weatherOutlook.ts from GET /api/weather-outlook (contract:
 * backend/app/weather_outlook/contract.py); components never see the raw API shape.
 *
 * It describes what the weather did after this date in past seasons at the site's
 * station. It is not a meteorological forecast.
 */

export type OutlookHorizon = 30 | 60 | 90 | 'season';

export type OutlookCategory = 'adverse' | 'typical' | 'favorable';

/** Whole percentages that sum to 100. */
export type OutlookProbabilities = Record<OutlookCategory, number>;

export interface OutlookOutcome {
  id: 'rain' | 'gdd' | 'heatDays' | 'drySpell' | 'waterDeficit';
  label: string;
  unit: string;
  /** 20th percentile, median, 80th percentile across the historical seasons. */
  low: number;
  median: number;
  high: number;
  decimals: number;
}

export interface RepresentativeSeason {
  category: OutlookCategory;
  season: number;
  rainIn: number | null;
  heatDays: number | null;
}

export interface WeatherOutlook {
  site: string;
  asOfDate: string;
  horizon: OutlookHorizon;
  horizonEnd: string;
  /** null when the backend could not form categories (it then says why in `categoryNote`). */
  probabilities: OutlookProbabilities | null;
  /** What favorable / typical / adverse are judged on, in the backend's words. */
  categoryBasis: string | null;
  categoryProvisional: boolean;
  categoryNote: string | null;
  historicalSeasons: number;
  firstSeason: number | null;
  lastSeason: number | null;
  effectiveSeasons: number;
  exploratory: boolean;
  /** true: every historical season counts equally (the backtest found no gain from weighting). */
  equalWeights: boolean;
  weightingNote: string | null;
  methodNote: string;
  stationName: string | null;
  stationSource: string | null;
  libraryLabel: string | null;
  plantingDate: string;
  outcomes: OutlookOutcome[];
  representative: RepresentativeSeason[];
  /** Growing degree days (°F, base 50) observed at the station from 1 April through the date. */
  gddToDate: number | null;
}

export type WeatherOutlookState =
  | { status: 'loading' }
  | { status: 'success'; outlook: WeatherOutlook }
  | { status: 'unavailable'; reason: string };
