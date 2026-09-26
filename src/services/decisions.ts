/**
 * Decision Support Service
 * Every plot at one point in the season, for choosing where to scout.
 * GET /api/decisions?asOfDate= in API mode; demo mode assembles the same shape from
 * the demo fields, mirroring MockForecastProvider.get_decisions in the backend.
 */

import type { DecisionSet, FieldForecast, ForecastSnapshot, PlotDecision } from '../types/agricultural';
import { ALL_FIELDS } from '../mock/fieldsData';
import { APP_CONFIG } from '../config/appConfig';
import { apiGet } from './apiClient';

/** Each plot at its latest forecast on or before `asOfDate`; nothing from after it is used. */
export async function getDecisions(asOfDate: string): Promise<DecisionSet> {
  if (!APP_CONFIG.demoMode) {
    return apiGet<DecisionSet>(`/decisions?asOfDate=${encodeURIComponent(asOfDate)}`);
  }
  const season = Number(asOfDate.slice(0, 4));
  const plots = ALL_FIELDS.filter((f) => f.field.season === season).flatMap((f) => {
    const eligible = f.snapshots.filter((s) => s.date <= asOfDate);
    return eligible.length ? [toDecision(f, eligible[eligible.length - 1], eligible[eligible.length - 2])] : [];
  });
  return { asOfDate, unit: 'bu/ac', intervalLevel: 0.9, plots };
}

function toDecision(f: FieldForecast, s: ForecastSnapshot, prior: ForecastSnapshot | undefined): PlotDecision {
  const negative = [...s.featureImportance].sort((a, b) => b.weight - a.weight).find((d) => d.direction === 'negative');
  return {
    fieldId: f.field.id,
    plotId: f.field.plotId,
    name: f.field.name,
    site: f.field.site,
    season: f.field.season,
    hybrid: f.field.hybrid,
    nitrogenLbAc: f.field.nitrogenLbAc,
    irrigationStatus: f.field.irrigationStatus,
    forecastDate: s.date,
    predictedYield: s.yield,
    lowerBound: s.lowerBound,
    upperBound: s.upperBound,
    confidence: s.confidence,
    confidenceRating: s.confidenceRating,
    previousForecastDate: prior?.date ?? null,
    previousYield: prior?.yield ?? null,
    changeSincePrevious: prior ? Math.round((s.yield - prior.yield) * 10) / 10 : null,
    topNegativeDriver: negative?.name ?? null,
  };
}
