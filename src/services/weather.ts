/**
 * Weather Context Service
 * Weather summaries and anomalies for a field and forecast date. Demo values
 * today; PRISM / NOAA are candidate sources once the backend API is in place.
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
