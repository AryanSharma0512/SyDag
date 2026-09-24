/**
 * Fields Service
 * Field metadata for the field selector. Demo data in demo mode, otherwise
 * GET /api/fields.
 */

import { FieldMeta } from '../types/agricultural';
import { ALL_FIELDS } from '../mock/fieldsData';
import { APP_CONFIG } from '../config/appConfig';
import { apiGet, ApiError } from './apiClient';

export async function getFields(): Promise<FieldMeta[]> {
  if (!APP_CONFIG.demoMode) return apiGet<FieldMeta[]>('/fields');
  return ALL_FIELDS.map((f) => f.field);
}

export async function getFieldById(fieldId: string): Promise<FieldMeta | null> {
  if (!APP_CONFIG.demoMode) {
    try {
      return await apiGet<FieldMeta>(`/fields/${encodeURIComponent(fieldId)}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  }
  const found = ALL_FIELDS.find((f) => f.field.id === fieldId);
  return found ? found.field : null;
}
