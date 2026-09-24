/**
 * Data Provenance Service
 * Returns the challenge-provided source and the candidate enrichments. Candidate
 * sources are listed for transparency; they are not connected yet.
 */

import { DataSource } from '../types/agricultural';
import { DATA_SOURCES } from '../mock/fieldsData';

export async function getDataSources(): Promise<DataSource[]> {
  return DATA_SOURCES;
}
