/**
 * Final Results Service
 * The frozen, versioned output of the final ML run (GET /api/results and
 * GET /api/results/plots; contract in backend/app/results.py). The website reads
 * precomputed results on purpose; replacing this module's source (e.g. with live
 * inference) leaves the components unchanged. The demo build has no results and
 * reports `pending` rather than inventing any.
 */

import type { FinalResults, MaturityEstimate, ResultPlot, StagePerformance } from '../types/results';
import { APP_CONFIG } from '../config/appConfig';
import { apiGet } from './apiClient';

const PENDING: FinalResults = {
  status: 'pending',
  contractVersion: 1,
  unit: 'bu/ac',
  performance: [],
  sites: [],
  plotCounts: [],
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
export function stageForDap(performance: StagePerformance[], dap: number | null): StagePerformance | null {
  if (dap === null) return null;
  const eligible = performance.filter((p) => p.dap <= dap);
  return eligible.length ? eligible[eligible.length - 1] : null;
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
