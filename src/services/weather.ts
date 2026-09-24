/**
 * Weather Context Service
 * Supplies meteorological enrichment and historical anomaly metrics.
 */

import { WeatherContext } from '../types/agricultural';
import { getForecast } from './forecasts';

export async function getWeatherContext(fieldId: string, snapshotId?: string): Promise<WeatherContext> {
  const forecast = await getForecast(fieldId);
  if (snapshotId) {
    const snap = forecast.snapshots.find((s) => s.id === snapshotId);
    if (snap) return snap.weather;
  }
  return forecast.snapshots[forecast.snapshots.length - 1].weather;
}
