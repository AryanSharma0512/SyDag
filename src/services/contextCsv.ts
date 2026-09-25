/**
 * CSV for demo builds only. Live builds download CSVs from GET /api/context/export,
 * which is the authority; demo builds have no backend, so this mirrors
 * backend/app/context/export.py over the recorded snapshot. Keep the two in step.
 */

import type { LocationContext } from '../types/agricultural';

export type ContextExportType = 'weather' | 'soil' | 'yield-history' | 'all';

type Cell = string | number | null | undefined;

function cell(value: Cell): string {
  const text = value === null || value === undefined ? '' : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function toCsv(columns: string[], rows: Cell[][]): string {
  return [columns, ...rows].map((row) => row.map(cell).join(',')).join('\n') + '\n';
}

/** The CSV for one dataset, or null when that source has no data in the context. */
export function contextCsv(context: LocationContext, type: ContextExportType): string | null {
  const { latitude: lat, longitude: lon } = context;
  const soil = context.soil.data;
  const weather = context.weather.data;
  const history = context.yieldHistory.data;

  if (type === 'weather') {
    if (!weather) return null;
    const { station } = weather;
    return toCsv(
      [
        'latitude', 'longitude', 'asOf', 'observedThrough', 'rainfallLast7DaysMm', 'rainfallLast30DaysMm',
        'avgTempLast30DaysF', 'gddSinceSeasonStart', 'heatDays', 'longestDrySpellDays', 'dataCompleteness',
        'seasonStart', 'stationId', 'stationName', 'stationDistanceKm', 'source', 'retrievedAt',
      ],
      weather.summaries.map((s) => [
        lat, lon, s.asOf, s.observedThrough, s.rainfallLast7DaysMm, s.rainfallLast30DaysMm,
        s.avgTempLast30DaysF, s.gddSinceSeasonStart, s.heatDays, s.longestDrySpellDays, s.dataCompleteness,
        s.seasonStart, station.id, station.name, station.distanceKm, weather.source, weather.retrievedAt,
      ]),
    );
  }
  if (type === 'soil') {
    if (!soil) return null;
    return toCsv(['property', 'value'], [['latitude', lat], ['longitude', lon], ...Object.entries(soil)]);
  }
  if (type === 'yield-history') {
    if (!history) return null;
    const { county } = history;
    return toCsv(
      ['latitude', 'longitude', 'year', 'yield', 'unit', 'county', 'stateCode', 'countyFips', 'source', 'retrievedAt'],
      history.years.map((y) => [
        lat, lon, y.year, y.yield, history.unit, county.name, county.stateCode, county.fips, history.source, history.retrievedAt,
      ]),
    );
  }

  const rows: Cell[][] = [
    ['location', '', 'latitude', lat],
    ['location', '', 'longitude', lon],
    ...Object.entries(context.county ?? {}).map(([key, value]) => ['location', '', key, value]),
  ];
  const parts = [
    ['soil', context.soil],
    ['weather', context.weather],
    ['yieldHistory', context.yieldHistory],
  ] as const;
  for (const [dataset, part] of parts) {
    rows.push([dataset, '', 'status', part.status]);
    if (part.message) rows.push([dataset, '', 'message', part.message]);
  }
  if (soil) rows.push(...Object.entries(soil).map(([key, value]) => ['soil', '', key, value]));
  if (weather) {
    rows.push(...Object.entries(weather.station).map(([key, value]) => ['weather', 'station', key, value]));
    rows.push(['weather', '', 'source', weather.source], ['weather', '', 'retrievedAt', weather.retrievedAt]);
    for (const summary of weather.summaries) {
      rows.push(...Object.entries(summary).map(([key, value]) => ['weather', summary.asOf, key, value]));
    }
  }
  if (history) {
    rows.push(
      ['yieldHistory', '', 'county', history.county.name],
      ['yieldHistory', '', 'countyFips', history.county.fips],
      ['yieldHistory', '', 'unit', history.unit],
      ['yieldHistory', '', 'fiveYearAverage', history.fiveYearAverage],
      ['yieldHistory', '', 'source', history.source],
      ['yieldHistory', '', 'retrievedAt', history.retrievedAt],
      ...history.years.map((y) => ['yieldHistory', y.year, 'yield', y.yield]),
    );
  }
  return toCsv(['dataset', 'record', 'property', 'value'], rows);
}
