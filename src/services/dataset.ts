/**
 * Dataset Label Service
 * The plain label for the data behind the forecasts ("Demo data", "Practice data").
 * In API mode it comes from the backend (GET /api/health), so it changes with the data.
 */

import { APP_CONFIG } from '../config/appConfig';
import { apiGet } from './apiClient';

export async function getDatasetLabel(): Promise<string> {
  if (APP_CONFIG.demoMode) return APP_CONFIG.datasetLabel;
  const health = await apiGet<{ datasetLabel: string }>('/health');
  return health.datasetLabel;
}
