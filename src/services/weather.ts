/**
 * Weather Context Service
 * Supplies meteorological enrichment and historical anomaly metrics.
 */

import { WeatherContext } from '../types/agricultural';
import { APP_CONFIG } from '../config/appConfig';
import { apiGet } from './apiClient';
import { getForecast } from './forecasts';

export async function getWeatherContext(fieldId: string, snapshotId?: string): Promise<WeatherContext> {
  if (!APP_CONFIG.demoMode) {
    const query = snapshotId ? `?snapshotId=${encodeURIComponent(snapshotId)}` : '';
    return apiGet<WeatherContext>(`/fields/${encodeURIComponent(fieldId)}/weather${query}`);
  }
  const forecast = await getForecast(fieldId);
  if (snapshotId) {
    const snap = forecast.snapshots.find((s) => s.id === snapshotId);
    if (snap) return snap.weather;
  }
  return forecast.snapshots[forecast.snapshots.length - 1].weather;
}
