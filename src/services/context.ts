/**
 * Location Context Service
 * Public data for a field's coordinates: soil (USDA SSURGO), observed weather
 * (NOAA NCEI) and county yields (USDA NASS). The backend fetches, normalizes and
 * caches these; components never call USDA or NOAA themselves.
 * Demo mode returns a snapshot of the same public data, otherwise GET /api/context/all.
 */

import type { FieldMeta, LocationContext } from '../types/agricultural';
import { CONTEXT_SNAPSHOT } from '../mock/contextSnapshot';
import { APP_CONFIG } from '../config/appConfig';
import { apiGet, apiGetFile } from './apiClient';
import { contextCsv, type ContextExportType } from './contextCsv';

export type { ContextExportType };

function contextQuery(field: FieldMeta, dates: string[]): URLSearchParams {
  const query = new URLSearchParams({ lat: String(field.latitude), lon: String(field.longitude) });
  dates.forEach((date) => query.append('date', date));
  return query;
}

/** Soil, county yields, and weather summarized as of each date (in the order given). */
export async function getLocationContext(field: FieldMeta, dates: string[]): Promise<LocationContext | null> {
  if (!APP_CONFIG.demoMode) {
    return apiGet<LocationContext>(`/context/all?${contextQuery(field, dates)}`);
  }
  return CONTEXT_SNAPSHOT[field.id] ?? null;
}

/**
 * The normalized data behind getLocationContext as a CSV file: one dataset, or all of
 * them. Live builds get it from GET /api/context/export; demo builds from the snapshot.
 */
export async function getLocationContextCsv(
  field: FieldMeta,
  dates: string[],
  type: ContextExportType,
): Promise<{ filename: string; blob: Blob }> {
  const filename = `soilsignal-${field.id}-${type}.csv`;
  if (!APP_CONFIG.demoMode) {
    const query = contextQuery(field, dates);
    query.set('type', type);
    return { filename, blob: await apiGetFile(`/context/export?${query}`) };
  }
  const snapshot = CONTEXT_SNAPSHOT[field.id];
  const csv = snapshot ? contextCsv(snapshot, type) : null;
  if (csv === null) throw new Error('This data is not available for this field.');
  return { filename, blob: new Blob([csv], { type: 'text/csv;charset=utf-8' }) };
}
