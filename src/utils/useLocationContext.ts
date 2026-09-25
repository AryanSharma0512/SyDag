import { useEffect, useState } from 'react';
import type { FieldMeta, LocationContext } from '../types/agricultural';
import { getLocationContext } from '../services/context';

/** A field's public data, tagged with the field it belongs to so stale results are easy to spot. */
export interface LoadedContext {
  fieldId: string;
  /** Null when the request itself failed (each source's own failures live inside the context). */
  data: LocationContext | null;
}

/**
 * Loads public data (soil, observed weather, county yields) once per field, covering
 * every date given so switching dates stays instant. Returns null until the first load;
 * compare `fieldId` with the current field to tell whether a newer load is pending.
 */
export function useLocationContext(field: FieldMeta | null, dates: string[]): LoadedContext | null {
  const [loaded, setLoaded] = useState<LoadedContext | null>(null);
  const dateKey = dates.join(',');

  useEffect(() => {
    if (!field || !dateKey) return;
    let active = true;
    getLocationContext(field, dateKey.split(','))
      .then((data) => active && setLoaded({ fieldId: field.id, data }))
      .catch(() => active && setLoaded({ fieldId: field.id, data: null }));
    return () => {
      active = false;
    };
  }, [field, dateKey]);

  return loaded;
}
