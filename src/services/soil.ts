/**
 * Soil Context Service
 * Supplies USDA NRCS SSURGO pedon surveys and moisture holding capacity metrics.
 */

import { SoilContext } from '../types/agricultural';
import { getForecast } from './forecasts';

export async function getSoilContext(fieldId: string): Promise<SoilContext> {
  const forecast = await getForecast(fieldId);
  return forecast.snapshots[0].soil;
}
