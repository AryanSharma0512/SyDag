/**
 * Plot Forecasts Service
 * One shape for a plot's yield forecasts through the season, whichever source serves it:
 *
 *   final   the frozen final results (GET /api/results/plots), when they cover the site
 *   live    the deployed models run on the input bundle (GET /api/fields/:id/forecast)
 *
 * The final results win for a site once they cover it. Components read PlotSeries and
 * never branch on where it came from, except to offer the live model's extra detail.
 */

import type { FieldForecast, FieldMeta, GrowthStage, ModelInfo } from '../types/agricultural';
import type { FinalResults, PlotUav, ResultForecastPoint, ResultPlot } from '../types/results';
import type { TrialSite } from '../types/sites';
import { ALL_FIELDS } from '../mock/fieldsData';
import { APP_CONFIG } from '../config/appConfig';
import { formatDay } from '../utils/formatters';
import { apiGet } from './apiClient';
import { getForecast } from './forecasts';
import { getResultPlots, stageForDap } from './results';

export type ForecastSource = 'final' | 'live';

export interface PlotOption {
  key: string;
  source: ForecastSource;
  plotId: string;
  label: string;
  detail: string; // hybrid and nitrogen, for the picker
  season: number;
  featured: boolean;
  /** Live plots load by field id; final plots are already in memory. */
  fieldId?: string;
  resultPlot?: ResultPlot;
  siteAverage?: { site: string; season: number };
}

export interface ForecastPoint {
  id: string;
  date: string;
  displayDate: string;
  dap: number | null;
  yield: number;
  lowerBound: number | null;
  upperBound: number | null;
  stage?: GrowthStage;
  stageSubtext?: string;
}

export interface PlotSeries {
  key: string;
  source: ForecastSource;
  siteId: string;
  season: number;
  plotId: string;
  isSiteAverage: boolean;
  hybrid?: string;
  nitrogenLbAc?: number;
  plantingDate?: string;
  irrigated?: boolean;
  points: ForecastPoint[];
  uav?: PlotUav | null;
  /** The live model's full forecast (vegetation, drivers, weather, soil), for "More detail". */
  live?: FieldForecast;
}

/** The demo build's own fields are not at a trial site; they form one pseudo-location. */
export const DEMO_SITE_ID = 'demo-fields';

export function demoSite(): TrialSite {
  const first = ALL_FIELDS[0]?.field;
  return {
    id: DEMO_SITE_ID,
    name: 'Demo fields',
    state: '',
    stateName: 'Demo data',
    latitude: first?.latitude ?? 0,
    longitude: first?.longitude ?? 0,
    coordinateSource: 'demo',
    crop: 'Maize',
    irrigated: false,
    seasons: [],
    forecasts: { livePlots: ALL_FIELDS.length, finalPlots: 0, finalSiteForecast: false, seasons: [APP_CONFIG.seasonYear] },
  };
}

export function daysAfterPlanting(plantingDate: string | null | undefined, date: string): number | null {
  if (!plantingDate) return null;
  const ms = Date.parse(`${date.slice(0, 10)}T00:00:00Z`) - Date.parse(`${plantingDate.slice(0, 10)}T00:00:00Z`);
  return Number.isFinite(ms) ? Math.round(ms / 86_400_000) : null;
}

function describe(hybrid?: string | null, nitrogen?: number | null): string {
  return [hybrid, nitrogen != null && `${Math.round(nitrogen)} lb N/ac`].filter(Boolean).join(' · ');
}

function fromResultPoints(key: string, points: ResultForecastPoint[]): ForecastPoint[] {
  return points.map((p, i) => ({
    id: `${key}:${i}`,
    date: p.date,
    displayDate: formatDay(p.date),
    dap: p.dap,
    yield: p.yield,
    lowerBound: p.lower ?? null,
    upperBound: p.upper ?? null,
  }));
}

function liveOption(f: FieldMeta, featured: boolean): PlotOption {
  const plotId = f.plotId ?? f.name;
  return {
    key: `live:${f.id}`,
    source: 'live',
    plotId,
    label: f.plotId ? `Plot ${f.plotId}` : f.name,
    detail: describe(f.hybrid, f.nitrogenLbAc) || f.location,
    season: f.season,
    featured,
    fieldId: f.id,
  };
}

/**
 * The plots with forecasts at a site in a season, featured plots first. Final results
 * replace the live models for any site they cover.
 */
export async function getSitePlots(site: TrialSite, results: FinalResults | null, season?: number): Promise<PlotOption[]> {
  if (site.id === DEMO_SITE_ID) return ALL_FIELDS.map((f) => liveOption(f.field, true));

  const f = site.forecasts;
  if (results?.status === 'ready' && f && f.finalPlots > 0) {
    const plots = await getResultPlots(site.id, season);
    return plots
      .map<PlotOption>((p) => ({
        key: `final:${p.site}:${p.season}:${p.plotId}`,
        source: 'final',
        plotId: p.plotId,
        label: `Plot ${p.plotId}`,
        detail: describe(p.hybrid, p.nitrogenLbAc),
        season: p.season,
        featured: false,
        resultPlot: p,
      }))
      .sort((a, b) => a.plotId.localeCompare(b.plotId, undefined, { numeric: true }));
  }
  if (results?.status === 'ready' && f?.finalSiteForecast) {
    const series = results.sites.find(
      (s) => s.site.toLowerCase() === site.id.toLowerCase() && (season === undefined || s.season === season),
    );
    if (series) {
      return [
        {
          key: `final-site:${series.site}:${series.season}`,
          source: 'final',
          plotId: 'All plots',
          label: 'All plots (site average)',
          detail: series.plots ? `${series.plots} plots` : '',
          season: series.season,
          featured: true,
          siteAverage: { site: series.site, season: series.season },
        },
      ];
    }
  }
  if (f && f.livePlots > 0 && !APP_CONFIG.demoMode) {
    const [all, featured] = await Promise.all([
      apiGet<FieldMeta[]>(`/fields?site=${encodeURIComponent(site.id)}`),
      apiGet<FieldMeta[]>('/fields'),
    ]);
    const featuredIds = new Set(featured.map((x) => x.id));
    return all
      .filter((x) => season === undefined || x.season === season)
      .map((x) => liveOption(x, featuredIds.has(x.id)))
      .sort((a, b) => Number(b.featured) - Number(a.featured) || a.plotId.localeCompare(b.plotId, undefined, { numeric: true }));
  }
  return [];
}

export async function getPlotSeries(option: PlotOption, site: TrialSite, results: FinalResults | null): Promise<PlotSeries> {
  if (option.resultPlot) {
    const p = option.resultPlot;
    return {
      key: option.key,
      source: 'final',
      siteId: site.id,
      season: p.season,
      plotId: p.plotId,
      isSiteAverage: false,
      hybrid: p.hybrid ?? undefined,
      nitrogenLbAc: p.nitrogenLbAc ?? undefined,
      plantingDate: p.plantingDate ?? undefined,
      irrigated: p.irrigated ?? undefined,
      points: fromResultPoints(option.key, p.forecasts),
      uav: p.uav ?? null,
    };
  }
  if (option.siteAverage) {
    const s = results?.sites.find((x) => x.site === option.siteAverage!.site && x.season === option.siteAverage!.season);
    if (!s) throw new Error(`The final results no longer carry a forecast for ${site.name}.`);
    return {
      key: option.key,
      source: 'final',
      siteId: site.id,
      season: s.season,
      plotId: option.plotId,
      isSiteAverage: true,
      irrigated: site.irrigated,
      points: fromResultPoints(option.key, s.forecasts),
    };
  }
  const forecast = await getForecast(option.fieldId!);
  const planting = forecast.field.plantingDate;
  return {
    key: option.key,
    source: 'live',
    siteId: site.id,
    season: forecast.field.season,
    plotId: option.plotId,
    isSiteAverage: false,
    hybrid: forecast.field.hybrid,
    nitrogenLbAc: forecast.field.nitrogenLbAc,
    plantingDate: planting,
    irrigated: forecast.field.irrigationStatus !== 'Dryland',
    points: forecast.snapshots.map((s) => ({
      id: s.id,
      date: s.date,
      displayDate: s.displayDate,
      dap: daysAfterPlanting(planting, s.date),
      yield: s.yield,
      lowerBound: s.lowerBound,
      upperBound: s.upperBound,
      stage: s.stage,
      stageSubtext: s.stageSubtext,
    })),
    live: forecast,
  };
}

export interface TypicalError {
  mae: number;
  /** Where the number comes from, in plain words. */
  basis: string;
}

/**
 * The validation error that applies to one forecast: the final results' MAE for the
 * matching stage, or, for the live models, the held-out-site MAE of the model that made
 * the forecast (its cross-validation MAE when there is no held-out test).
 */
export function typicalError(
  series: PlotSeries,
  point: ForecastPoint,
  results: FinalResults | null,
  models: ModelInfo[] | null,
): TypicalError | null {
  if (series.source === 'final') {
    const stage = results?.status === 'ready' ? stageForDap(results.performance, point.dap) : null;
    return stage?.mae != null ? { mae: stage.mae, basis: `in validation, ${stage.dap} days after planting` } : null;
  }
  const model = models?.find((m) => m.asOf === point.date.slice(5));
  if (!model) return null;
  if (model.holdout) {
    return { mae: model.holdout.mae, basis: `on the held-out ${model.holdout.group.replace(/^site:\s*/i, '')} site` };
  }
  return { mae: model.mae, basis: 'in cross-validation' };
}

/** The point to open on: the earliest useful stage the final results name, else the latest. */
export function defaultPointIndex(points: ForecastPoint[], results: FinalResults | null, source: ForecastSource): number {
  if (!points.length) return 0;
  const target = source === 'final' && results?.status === 'ready' ? results.earliestUsefulDap : null;
  if (target != null) {
    const at = points.findIndex((p) => p.dap !== null && p.dap >= target);
    if (at >= 0) return at;
  }
  if (source === 'live') return Math.min(APP_CONFIG.defaultDateIndex, points.length - 1);
  return points.length - 1;
}
