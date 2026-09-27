/**
 * Final Results Service
 * The frozen, versioned output of the final ML run (GET /api/results and
 * GET /api/results/plots; contract in backend/app/results.py). The website reads
 * precomputed results on purpose; replacing this module's source (e.g. with live
 * inference) leaves the components unchanged. The demo build has no results and
 * reports `pending` rather than inventing any.
 */

import type {
  FinalResults,
  MaturityEstimate,
  ResultPlot,
  SitePerformance,
  SiteStage,
  ValidationMetrics,
} from '../types/results';
import { APP_CONFIG } from '../config/appConfig';
import { apiGet } from './apiClient';

const PENDING: FinalResults = {
  status: 'pending',
  contractVersion: 1,
  unit: 'bu/ac',
  performance: [],
  sites: [],
  plotCounts: [],
  sitePerformance: [],
  maturity: [],
  uav: null,
};

let summary: Promise<FinalResults> | null = null;

export function getFinalResults(): Promise<FinalResults> {
  if (APP_CONFIG.demoMode) return Promise.resolve(PENDING);
  if (!summary) {
    summary = apiGet<FinalResults>('/results').catch((err: unknown) => {
      summary = null;
      throw err;
    });
  }
  return summary;
}

const plotCache = new Map<string, Promise<ResultPlot[]>>();

export function getResultPlots(site: string, season?: number): Promise<ResultPlot[]> {
  if (APP_CONFIG.demoMode) return Promise.resolve([]);
  const params = new URLSearchParams({ site });
  if (season !== undefined) params.set('season', String(season));
  const key = params.toString();
  let request = plotCache.get(key);
  if (!request) {
    request = apiGet<ResultPlot[]>(`/results/plots?${key}`).catch((err: unknown) => {
      plotCache.delete(key);
      throw err;
    });
    plotCache.set(key, request);
  }
  return request;
}

/**
 * The validation stage a forecast at `dap` days after planting corresponds to: the
 * latest stage at or before it. Earlier than every stage there is no matching result.
 */
export function stageForDap<T extends { dap: number }>(performance: T[], dap: number | null): T | null {
  if (dap === null) return null;
  const eligible = performance.filter((p) => p.dap <= dap);
  return eligible.length ? eligible[eligible.length - 1] : null;
}

/**
 * The validation row for one forecast: by its stage key when both carry one (a plot's own
 * DAP can sit a day or two either side of the stage's), else by DAP.
 */
export function stageRow<T extends { dap: number; stage?: string | null }>(
  rows: T[],
  stage: string | null | undefined,
  dap: number | null,
): T | null {
  if (stage) {
    const match = rows.find((r) => r.stage === stage);
    if (match) return match;
  }
  return stageForDap(rows, dap);
}

/** One site's own validation for the season, when the results carry it. */
export function sitePerformanceFor(
  results: FinalResults | null,
  site: string | null | undefined,
  season?: number | null,
): SitePerformance | null {
  if (!results || results.status !== 'ready' || !site) return null;
  const key = site.toLowerCase();
  return (
    results.sitePerformance.find((s) => s.site.toLowerCase() === key && (season == null || s.season === season)) ?? null
  );
}

/** The stage whose error first comes within `margin` of the site's best: where the site levels off. */
export function plateauStage(site: SitePerformance, metric: 'r2' | 'mae' = 'r2', margin = 0.02): SiteStage | null {
  const rows = site.stages.filter((s) => s[metric] != null);
  if (!rows.length) return null;
  const values = rows.map((s) => s[metric] as number);
  const best = metric === 'r2' ? Math.max(...values) : Math.min(...values);
  return rows.find((s) => (metric === 'r2' ? best - (s.r2 as number) : (s.mae as number) - best) <= margin) ?? null;
}

export type ImageryGain = 'little' | 'modest' | 'clear';

/**
 * How much satellite imagery lowered typical error against the site's field-records-only
 * baseline, in words that do not overclaim: under 5% is "little", under 15% "modest".
 */
export function imageryGain(preseason: ValidationMetrics | null | undefined, stage: ValidationMetrics | null | undefined): ImageryGain | null {
  if (preseason?.mae == null || stage?.mae == null || preseason.mae <= 0) return null;
  const gain = (preseason.mae - stage.mae) / preseason.mae;
  return gain < 0.05 ? 'little' : gain < 0.15 ? 'modest' : 'clear';
}

/** Total dated forecasts (plot observations) across the published plots. */
export function observationCount(results: FinalResults | null): number {
  return results?.status === 'ready' ? results.plotCounts.reduce((n, c) => n + (c.observations ?? 0), 0) : 0;
}

/** A plot's own maturity estimate, else its site's, for the season. */
export function maturityFor(
  results: FinalResults | null,
  site: string,
  season: number,
  plotId?: string | null,
): MaturityEstimate | null {
  if (!results || results.status !== 'ready') return null;
  const here = results.maturity.filter((m) => m.site.toLowerCase() === site.toLowerCase() && m.season === season);
  return here.find((m) => plotId && m.plotId === plotId) ?? here.find((m) => !m.plotId) ?? null;
}
