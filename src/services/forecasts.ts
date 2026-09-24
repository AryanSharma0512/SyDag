/**
 * Forecasts Service
 * The single entry point for forecast data: snapshots through the season,
 * vegetation observations, events, explanations and historical context.
 * Demo data in demo mode, otherwise GET /api/fields/:fieldId/forecast.
 */

import { FieldForecast } from '../types/agricultural';
import { ALL_FIELDS, PURDUE_104_DATA } from '../mock/fieldsData';
import { APP_CONFIG } from '../config/appConfig';
import { apiGet } from './apiClient';

export async function getForecast(fieldId: string): Promise<FieldForecast> {
  if (!APP_CONFIG.demoMode) {
    return apiGet<FieldForecast>(`/fields/${encodeURIComponent(fieldId)}/forecast`);
  }
  const match = ALL_FIELDS.find((item) => item.field.id === fieldId);
  return match || PURDUE_104_DATA;
}

export async function getAvailableDates(fieldId: string): Promise<Array<{ id: string; date: string; displayDate: string }>> {
  const forecast = await getForecast(fieldId);
  return forecast.snapshots.map((s) => ({
    id: s.id,
    date: s.date,
    displayDate: s.displayDate,
  }));
}
