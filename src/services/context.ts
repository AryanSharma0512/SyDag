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
import { apiGet } from './apiClient';

/** Soil, county yields, and weather summarized as of each date (in the order given). */
export async function getLocationContext(field: FieldMeta, dates: string[]): Promise<LocationContext | null> {
  if (!APP_CONFIG.demoMode) {
    const query = new URLSearchParams({ lat: String(field.latitude), lon: String(field.longitude) });
    dates.forEach((date) => query.append('date', date));
    return apiGet<LocationContext>(`/context/all?${query}`);
  }
  return CONTEXT_SNAPSHOT[field.id] ?? null;
}
