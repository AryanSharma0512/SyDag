/**
 * Satellite passes as the forecast sees them. Passes are the dates of the plot's
 * vegetation observations; a forecast date "has" every pass on or before it. Pass
 * dates differ by site, so forecasts are described by pass count, never by month.
 */

import type { FieldForecast } from '../types/agricultural';
import { formatDay } from './formatters';

/** Sorted, unique acquisition dates (ISO). */
export function passDates(forecast: FieldForecast): string[] {
  return [...new Set(forecast.fullVegetationSeries.map((o) => o.date))].sort();
}

export function passesBy(passes: string[], isoDate: string): number {
  return passes.filter((p) => p <= isoDate).length;
}

/** "Before imagery", "After pass 1", … for a forecast date. */
export function imageryLabel(passes: string[], isoDate: string): string {
  const n = passesBy(passes, isoDate);
  return n === 0 ? 'Before imagery' : `After pass ${n}`;
}

/** Planting date from the trial record, else the planting event if the data has one. */
export function plantingDate(forecast: FieldForecast): string | undefined {
  return (
    forecast.field.plantingDate ??
    forecast.events.find((e) => e.type === 'management' && /plant/i.test(e.title))?.date
  );
}

export function satellitePlatform(forecast: FieldForecast): string | undefined {
  return forecast.spatial?.satellitePlatform ?? forecast.snapshots.find((s) => s.spatial)?.spatial?.satellitePlatform;
}

/** Hover text for one pass. Pléiades Neo is the six-band sensor in the trial datasets. */
export function passDescription(platform: string | undefined): string {
  if (!platform) return 'Satellite image';
  return /pl[ée]iades neo/i.test(platform) ? '6-band Pléiades Neo imagery' : `${platform} imagery`;
}

/** "Jul 31, 2022" */
export function formatFullDay(isoDate: string): string {
  return `${formatDay(isoDate)}, ${isoDate.slice(0, 4)}`;
}
