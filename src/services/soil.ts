/**
 * Soil Context Service
 * Soil properties for a field. Demo values today; USDA SSURGO is a candidate
 * source once the backend API is in place.
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
