/**
 * Forecasts Service
 * Decouples forecast intelligence retrieval from UI components.
 * Standard interface for getting time-series forecast snapshots, vegetation points, and explanations.
 */

import { FieldForecast } from '../types/agricultural';
import { ALL_FIELDS, PURDUE_104_DATA } from '../mock/fieldsData';

export async function getForecast(fieldId: string): Promise<FieldForecast> {
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
