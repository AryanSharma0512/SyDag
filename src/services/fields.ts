/**
 * Fields Service
 * Field metadata for the field selector. Resolves demo data today and is ready
 * to be swapped for GET /api/fields.
 */

import { FieldMeta } from '../types/agricultural';
import { ALL_FIELDS } from '../mock/fieldsData';

export async function getFields(): Promise<FieldMeta[]> {
  return ALL_FIELDS.map((f) => f.field);
}

export async function getFieldById(fieldId: string): Promise<FieldMeta | null> {
  const found = ALL_FIELDS.find((f) => f.field.id === fieldId);
  return found ? found.field : null;
}
