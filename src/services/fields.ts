/**
 * Fields Service
 * Decouples field metadata access. Currently resolves centralized mock data,
 * ready to be swapped with GET /api/fields when backend arrives.
 */

import { FieldMeta } from '../types/agricultural';
import { ALL_FIELDS } from '../mock/fieldsData';

export async function getFields(): Promise<FieldMeta[]> {
  // Simulates instant or fast network response without artificial delays
  return ALL_FIELDS.map((f) => f.field);
}

export async function getFieldById(fieldId: string): Promise<FieldMeta | null> {
  const found = ALL_FIELDS.find((f) => f.field.id === fieldId);
  return found ? found.field : null;
}
