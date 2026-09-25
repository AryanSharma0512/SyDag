/**
 * Data Provenance Service
 * Demo mode: the demo source list. API mode: the sources the backend reports for the
 * forecast (practice or challenge data, connected public data, model output), so the
 * page never describes data the forecast did not use.
 */

import type { DataSource, FieldForecast } from '../types/agricultural';
import { DATA_SOURCES } from '../mock/fieldsData';
import { APP_CONFIG } from '../config/appConfig';

export async function getDataSources(forecast?: FieldForecast | null): Promise<DataSource[]> {
  if (!APP_CONFIG.demoMode) return forecast?.sources ?? [];
  return DATA_SOURCES;
}
