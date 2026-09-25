import { useState, type ReactNode } from 'react';
import type { ContextPart, ObservedWeather, WeatherSummary } from '../../types/agricultural';
import { SegmentedControl } from '../common/SegmentedControl';
import { formatDay, formatNumber } from '../../utils/formatters';
import { SeasonChart, type ChartSeries } from './SeasonChart';
import { DataPanel, DataTable, Lineage, NotReported, type Column, type SourceState } from './DataPanel';

type View = 'rainfall' | 'temperature' | 'gdd' | 'stress';

// Muted blues for rain (30-day holds the 7-day inside it); warm pair for stress.
const RAIN_30 = '#7fa3c6';
const RAIN_7 = '#325576';
const WEATHER_LINE = '#3f6a93';
const HEAT = '#b8574a';
const DRY = '#c9a063';

const OBSERVED = ['Daily precipitation', 'Daily high temperature', 'Daily low temperature'];
const DERIVED = [
  '7-day rainfall',
  '30-day rainfall',
  '30-day average temperature',
  'Growing degree days',
  'Heat days',
  'Longest dry spell',
  'Data completeness',
];

const percent = (share: number) => `${Math.round(share * 100)}%`;

function chartFor(view: View, summaries: WeatherSummary[]) {
  const labels = summaries.map((s) => formatDay(s.asOf));
  const pick = (id: string, label: string, color: string, value: (s: WeatherSummary) => number | null): ChartSeries => ({
    id,
    label,
    color,
    values: summaries.map(value),
  });
  switch (view) {
    case 'rainfall':
      return (
        <SeasonChart
          labels={labels}
          kind="nested"
          unit="mm"
          decimals={1}
          ariaLabel="Rainfall in the 30 and 7 days before each forecast date"
          series={[
            pick('rain30', '30-day rainfall', RAIN_30, (s) => s.rainfallLast30DaysMm),
            pick('rain7', '7-day rainfall', RAIN_7, (s) => s.rainfallLast7DaysMm),
          ]}
        />
      );
    case 'temperature':
      return (
        <SeasonChart
          labels={labels}
          kind="line"
          unit="°F"
          decimals={1}
          ariaLabel="Average temperature over the 30 days before each forecast date"
          series={[pick('temp', '30-day average temperature', WEATHER_LINE, (s) => s.avgTempLast30DaysF)]}
        />
      );
    case 'gdd':
      return (
        <SeasonChart
          labels={labels}
          kind="line"
          unit="GDD"
          ariaLabel="Growing degree days accumulated since the season start"
          series={[pick('gdd', 'accumulated since season start', WEATHER_LINE, (s) => s.gddSinceSeasonStart)]}
        />
      );
    case 'stress':
      return (
        <SeasonChart
          labels={labels}
          kind="bars"
          unit="days"
          ariaLabel="Heat days and longest dry spell since the season start"
          footer={{ label: 'Complete', values: summaries.map((s) => percent(s.dataCompleteness)) }}
          series={[
            pick('heat', 'Heat days (≥ 95°F)', HEAT, (s) => s.heatDays),
            pick('dry', 'Longest dry spell (< 1 mm a day)', DRY, (s) => s.longestDrySpellDays),
          ]}
        />
      );
  }
}

const COLUMNS: Column<WeatherSummary>[] = [
  { key: 'asOf', label: 'As of', render: (s) => <span className="data">{formatDay(s.asOf)}</span> },
  {
    key: 'observedThrough',
    label: 'Observed through',
    render: (s) => (s.observedThrough ? <span className="data">{formatDay(s.observedThrough)}</span> : <NotReported />),
  },
  { key: 'rain7', label: 'Rain 7d (mm)', numeric: true, render: (s) => formatNumber(s.rainfallLast7DaysMm, 1) },
  { key: 'rain30', label: 'Rain 30d (mm)', numeric: true, render: (s) => formatNumber(s.rainfallLast30DaysMm, 1) },
  {
    key: 'temp',
    label: 'Avg temp 30d (°F)',
    numeric: true,
    render: (s) => (s.avgTempLast30DaysF === null ? <NotReported /> : formatNumber(s.avgTempLast30DaysF, 1)),
  },
  { key: 'gdd', label: 'GDD', numeric: true, render: (s) => formatNumber(s.gddSinceSeasonStart) },
  { key: 'heat', label: 'Heat days', numeric: true, render: (s) => s.heatDays },
  { key: 'dry', label: 'Dry spell (days)', numeric: true, render: (s) => s.longestDrySpellDays },
  { key: 'complete', label: 'Completeness', numeric: true, render: (s) => percent(s.dataCompleteness) },
];

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-[12px] text-muted">{label}</dt>
      <dd className="mt-1 text-[15px] text-ink">{children}</dd>
    </div>
  );
}

interface WeatherPanelProps {
  part: ContextPart<ObservedWeather> | null;
  state: SourceState;
  showData: boolean;
}

export function WeatherPanel({ part, state, showData }: WeatherPanelProps) {
  const [view, setView] = useState<View>('rainfall');
  const weather = part?.data;
  const summaries = weather?.summaries ?? [];
  const seasonStart = summaries[0]?.seasonStart;

  return (
    <DataPanel
      id="weather"
      source="weather"
      title="Observed weather"
      subtitle="Daily station records from the nearest NOAA station, summarized by SoilSignal for each forecast date."
      state={state}
      message={part?.message ?? null}
      lineage={
        weather && <Lineage source={weather.source} retrievedAt={weather.retrievedAt} observed={OBSERVED} derived={DERIVED} />
      }
    >
      {weather && (
        <>
          <dl className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4">
            <Fact label="Station">{weather.station.name}</Fact>
            <Fact label="Distance from field">
              <span className="data">{formatNumber(weather.station.distanceKm, 1)}</span> km
            </Fact>
            <Fact label="Station ID">
              <span className="data">{weather.station.id}</span>
            </Fact>
            <Fact label="Station location">
              <span className="data text-[14px]">
                {weather.station.latitude.toFixed(4)}, {weather.station.longitude.toFixed(4)}
              </span>
            </Fact>
          </dl>

          <div className="mt-8">
            {showData ? (
              <DataTable caption="Weather summaries by forecast date" columns={COLUMNS} rows={summaries} rowKey={(s) => s.asOf} />
            ) : (
              <>
                <div className="-mx-4 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
                  <SegmentedControl
                    ariaLabel="Weather measure"
                    size="sm"
                    value={view}
                    onChange={setView}
                    options={[
                      { value: 'rainfall', label: 'Rainfall' },
                      { value: 'temperature', label: 'Temperature' },
                      { value: 'gdd', label: 'Growing degree days' },
                      { value: 'stress', label: 'Stress' },
                    ]}
                  />
                </div>
                <div className="mt-6">{chartFor(view, summaries)}</div>
              </>
            )}
            <p className="mt-4 text-[12px] leading-relaxed text-muted">
              Each date summarizes the station's days up to that date.
              {seasonStart && ` Season totals (GDD, heat days, dry spell) count from ${formatDay(seasonStart)}.`} GDD uses base
              50°F, capped at 86°F.
            </p>
          </div>
        </>
      )}
    </DataPanel>
  );
}
