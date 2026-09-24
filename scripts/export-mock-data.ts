/**
 * Exports the frontend mock dataset to JSON for the backend's mock provider.
 * Run with `npm run export:mock` whenever src/mock/fieldsData.ts changes.
 */

import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ALL_FIELDS } from '../src/mock/fieldsData';

const outPath = resolve(import.meta.dirname, '../backend/data/mock/fields.json');
writeFileSync(outPath, JSON.stringify(ALL_FIELDS, null, 2) + '\n');
console.log(`Wrote ${ALL_FIELDS.length} field forecasts to ${outPath}`);
