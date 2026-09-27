/**
 * Dataset Label Service
 * The plain label for the data behind the forecasts ("Demo data", "Practice data").
 * In API mode it comes from the backend, so it changes with the data.
 */

import { APP_CONFIG } from '../config/appConfig';
import { apiGet } from './apiClient';
import { getFinalResults } from './results';

/** What the deployed models run on (GET /api/health): labels live-model views. */
export async function getDatasetLabel(): Promise<string> {
  if (APP_CONFIG.demoMode) return APP_CONFIG.datasetLabel;
  const health = await apiGet<{ datasetLabel: string }>('/health');
  return health.datasetLabel;
}

/** What the site as a whole shows: the published final results' data once they exist. */
export async function getSiteDatasetLabel(): Promise<string> {
  if (APP_CONFIG.demoMode) return APP_CONFIG.datasetLabel;
  const results = await getFinalResults().catch(() => null);
  if (results?.status === 'ready' && results.datasetLabel) return results.datasetLabel;
  return getDatasetLabel();
}
