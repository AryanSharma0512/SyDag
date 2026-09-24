/**
 * Soil Context Service
 * Supplies USDA NRCS SSURGO pedon surveys and moisture holding capacity metrics.
 */

import { SoilContext } from '../types/agricultural';
import { APP_CONFIG } from '../config/appConfig';
import { apiGet } from './apiClient';
import { getForecast } from './forecasts';

export async function getSoilContext(fieldId: string): Promise<SoilContext> {
  if (!APP_CONFIG.demoMode) {
    return apiGet<SoilContext>(`/fields/${encodeURIComponent(fieldId)}/soil`);
  }
  const forecast = await getForecast(fieldId);
  return forecast.snapshots[0].soil;
}
