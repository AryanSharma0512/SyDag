/**
 * Historical Weather Outlook Service
 * Wraps GET /api/weather-outlook (backend/app/weather_outlook/contract.py) and returns
 * the website's own WeatherOutlook shape, so components never depend on the raw API.
 * There is no fallback: the demo build and any API error report `unavailable`.
 */

import type {
  OutlookCategory,
  OutlookHorizon,
  OutlookOutcome,
  OutlookProbabilities,
  RepresentativeSeason,
  WeatherOutlook,
} from '../types/weatherOutlook';
import { APP_CONFIG } from '../config/appConfig';
import { apiGet, ApiError } from './apiClient';

export const OUTLOOK_HORIZONS: OutlookHorizon[] = [30, 60, 90, 'season'];

export function horizonLabel(horizon: OutlookHorizon): string {
  return horizon === 'season' ? 'Rest of season' : `Next ${horizon} days`;
}

// ---- raw API shape (contractVersion 1); private to this module --------------------

interface RawSummary {
  mean?: number | null;
  p20?: number | null;
  median?: number | null;
  p80?: number | null;
}

interface RawOutlook {
  contractVersion: number;
  site: string;
  asOfDate: string;
  horizonDays: number | 'season';
  horizonEnd: string;
  plantingDate: string;
  method: string;
  methodNote: string;
  weighting?: string | null;
  libraryLabel?: string | null;
  station?: { id?: string | null; name?: string | null; source?: string | null };
  historicalSeasons: number;
  seasonsUsed?: number[];
  effectiveSampleSize: number;
  exploratory: boolean;
  seasonToDate?: Record<string, number | null>;
  categoryBasis?: { description?: string; provisional?: boolean; available?: boolean; reason?: string | null };
  probabilities?: Record<OutlookCategory, number> | null;
  weatherSummary?: Record<string, RawSummary>;
  representativeScenarios?: Record<OutlookCategory, { season: number; outcomes?: Record<string, number | null> } | null>;
}

const MM_PER_INCH = 25.4;
const CATEGORIES: OutlookCategory[] = ['adverse', 'typical', 'favorable'];

/** Probabilities arrive as fractions; show whole percentages that still add to 100. */
function toPercentages(raw: Record<OutlookCategory, number>): OutlookProbabilities {
  const exact = CATEGORIES.map((c) => Math.max(0, raw[c] ?? 0) * 100);
  const total = exact.reduce((a, b) => a + b, 0) || 1;
  const scaled = exact.map((v) => (v / total) * 100);
  const floors = scaled.map(Math.floor);
  let remainder = 100 - floors.reduce((a, b) => a + b, 0);
  const order = scaled.map((v, i) => ({ i, frac: v - floors[i] })).sort((a, b) => b.frac - a.frac);
  for (const { i } of order) {
    if (remainder <= 0) break;
    floors[i] += 1;
    remainder -= 1;
  }
  return { adverse: floors[0], typical: floors[1], favorable: floors[2] };
}

const OUTCOMES: Array<{
  id: OutlookOutcome['id'];
  key: string;
  label: string;
  unit: string;
  decimals: number;
  convert?: (v: number) => number;
}> = [
  { id: 'rain', key: 'precipitationMm', label: 'Rainfall', unit: 'in', decimals: 1, convert: (v) => v / MM_PER_INCH },
  { id: 'gdd', key: 'gdd', label: 'Growing degree days', unit: 'GDD', decimals: 0 },
  { id: 'heatDays', key: 'heatDays', label: 'Days at 95 °F+', unit: 'days', decimals: 0 },
  { id: 'drySpell', key: 'longestDrySpellDays', label: 'Longest dry spell', unit: 'days', decimals: 0 },
  {
    id: 'waterDeficit',
    key: 'waterDeficitMm',
    label: 'Crop water deficit',
    unit: 'in',
    decimals: 1,
    convert: (v) => v / MM_PER_INCH,
  },
];

function outcomes(summary: Record<string, RawSummary> | undefined): OutlookOutcome[] {
  if (!summary) return [];
  return OUTCOMES.flatMap(({ id, key, label, unit, decimals, convert }) => {
    const s = summary[key];
    if (!s || s.p20 == null || s.median == null || s.p80 == null) return [];
    const f = convert ?? ((v: number) => v);
    return [{ id, label, unit, decimals, low: f(s.p20), median: f(s.median), high: f(s.p80) }];
  });
}

function representative(raw: RawOutlook['representativeScenarios']): RepresentativeSeason[] {
  if (!raw) return [];
  return CATEGORIES.flatMap((category) => {
    const s = raw[category];
    if (!s) return [];
    const rain = s.outcomes?.precipitationMm;
    return [
      {
        category,
        season: s.season,
        rainIn: rain == null ? null : rain / MM_PER_INCH,
        heatDays: s.outcomes?.heatDays ?? null,
      },
    ];
  });
}

function toOutlook(raw: RawOutlook): WeatherOutlook {
  const basis = raw.categoryBasis ?? {};
  const seasons = raw.seasonsUsed ?? [];
  return {
    site: raw.site,
    asOfDate: raw.asOfDate,
    horizon: raw.horizonDays === 'season' ? 'season' : (raw.horizonDays as OutlookHorizon),
    horizonEnd: raw.horizonEnd,
    probabilities: raw.probabilities && basis.available !== false ? toPercentages(raw.probabilities) : null,
    categoryBasis: basis.description ?? null,
    categoryProvisional: basis.provisional ?? false,
    categoryNote: basis.reason ?? null,
    historicalSeasons: raw.historicalSeasons,
    firstSeason: seasons.length ? Math.min(...seasons) : null,
    lastSeason: seasons.length ? Math.max(...seasons) : null,
    effectiveSeasons: raw.effectiveSampleSize,
    exploratory: raw.exploratory,
    equalWeights: raw.method === 'climatology',
    weightingNote: raw.weighting ?? null,
    methodNote: raw.methodNote,
    stationName: raw.station?.name ?? null,
    stationSource: raw.station?.source ?? null,
    libraryLabel: raw.libraryLabel ?? null,
    plantingDate: raw.plantingDate,
    outcomes: outcomes(raw.weatherSummary),
    representative: representative(raw.representativeScenarios),
    gddToDate: raw.seasonToDate?.gddToDate ?? null,
  };
}

export class OutlookUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OutlookUnavailable';
  }
}

const cache = new Map<string, Promise<WeatherOutlook>>();

/**
 * The outlook for a weather-library site (TrialSite.weather.librarySite) on a date.
 * Rejects with OutlookUnavailable (a plain-language reason) rather than inventing data.
 */
export function getWeatherOutlook(
  librarySite: string,
  asOfDate: string,
  horizon: OutlookHorizon,
  plantingDate?: string,
): Promise<WeatherOutlook> {
  if (APP_CONFIG.demoMode) {
    return Promise.reject(new OutlookUnavailable('The historical weather outlook needs the SoilSignal API.'));
  }
  const params = new URLSearchParams({ site: librarySite, asOfDate, horizonDays: String(horizon) });
  if (plantingDate) params.set('plantingDate', plantingDate);
  const key = params.toString();
  let request = cache.get(key);
  if (!request) {
    request = apiGet<RawOutlook>(`/weather-outlook?${key}`)
      .then(toOutlook)
      .catch((err: unknown) => {
        cache.delete(key);
        if (err instanceof ApiError && err.status === 422) {
          throw new OutlookUnavailable(
            `This window runs past the part of the growing season the outlook covers (${err.message}). Choose a shorter one.`,
          );
        }
        if (err instanceof ApiError && err.status === 404) {
          throw new OutlookUnavailable(`No weather history for this location (${err.message}).`);
        }
        if (err instanceof ApiError && err.status === 503) {
          throw new OutlookUnavailable('The weather history library is not loaded on this server.');
        }
        throw new OutlookUnavailable(err instanceof Error ? err.message : String(err));
      });
    cache.set(key, request);
  }
  return request;
}
