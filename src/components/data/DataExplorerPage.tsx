import { useEffect, useMemo, useState } from 'react';
import type { FieldForecast, FieldMeta } from '../../types/agricultural';
import { getFields } from '../../services/fields';
import { getForecast } from '../../services/forecasts';
import { APP_CONFIG } from '../../config/appConfig';
import { useLocationContext } from '../../utils/useLocationContext';
import { FieldSelector } from '../common/FieldSelector';
import { SegmentedControl } from '../common/SegmentedControl';
import { SOURCE_META, StatusLabel, type SourceKey, type SourceState } from './DataPanel';
import { ExportMenu } from './ExportMenu';
import { WeatherPanel } from './WeatherPanel';
import { SoilPanel } from './SoilPanel';
import { YieldPanel } from './YieldPanel';

type Mode = 'visual' | 'data';

const SOURCE_ORDER: Array<{ key: SourceKey; anchor: string }> = [
  { key: 'weather', anchor: 'weather' },
  { key: 'soil', anchor: 'soil' },
  { key: 'yieldHistory', anchor: 'yield-history' },
];

const coordinate = (value: number) => value.toFixed(4);

/**
 * What public data SoilSignal retrieved for a field, where it came from, and what the
 * backend derived from it. Uses the same /api/context/all response as the dashboard;
 * each source's status comes from that response, never from static metadata.
 */
export function DataExplorerPage() {
  const [fields, setFields] = useState<FieldMeta[]>([]);
  const [fieldId, setFieldId] = useState(APP_CONFIG.defaultFieldId);
  const [forecast, setForecast] = useState<FieldForecast | null>(null);
  const [mode, setMode] = useState<Mode>('visual');

  useEffect(() => {
    let active = true;
    getFields().then((list) => active && setFields(list));
    return () => {
      active = false;
    };
  }, []);

  // The field's forecast dates decide which days the weather is summarized for.
  useEffect(() => {
    let active = true;
    getForecast(fieldId).then((data) => active && setForecast(data));
    return () => {
      active = false;
    };
  }, [fieldId]);

  const field = forecast?.field ?? null;
  const dates = useMemo(() => forecast?.snapshots.map((s) => s.date) ?? [], [forecast]);
  const loaded = useLocationContext(field, dates);
  const current = loaded && field && loaded.fieldId === field.id ? loaded : null;
  const context = current?.data ?? null;

  const stateOf = (key: SourceKey): SourceState => {
    if (!current) return 'loading';
    return context ? context[key].status : 'unavailable';
  };
  const states = { weather: stateOf('weather'), soil: stateOf('soil'), yieldHistory: stateOf('yieldHistory') };
  const connected = Object.values(states).filter((s) => s === 'ok').length;
  const requestFailed = current !== null && context === null;
  const partOf = <K extends SourceKey>(key: K) => context?.[key] ?? null;
  const failureMessage = requestFailed ? 'The SoilSignal backend did not return public data for this field.' : null;

  return (
    <div className="mx-auto max-w-6xl px-4 pt-8 pb-24 sm:px-6 sm:pt-10">
      <header>
        <h1 className="text-[28px] font-semibold tracking-[-0.02em] text-ink sm:text-[32px]">Data Explorer</h1>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
          Explore the public environmental and agricultural data SoilSignal uses to understand each field.
        </p>
      </header>

      {field ? (
        <>
          <div className="mt-10 flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
            <div className="min-w-0">
              <FieldSelector fields={fields.length ? fields : [field]} field={field} onSelectField={setFieldId} />
              <p className="mt-1.5 text-[14px] text-muted">
                <span className="data text-ink-soft">
                  {coordinate(field.latitude)}, {coordinate(field.longitude)}
                </span>
                {' · '}
                {context?.county ? `${context.county.name}, ${context.county.stateCode}` : field.location}
              </p>
              <p className="mt-3 text-[14px] text-ink-soft" aria-live="polite">
                {!current
                  ? 'Checking public data sources…'
                  : connected === 3
                    ? '3 public data sources connected'
                    : `${connected} of 3 public data sources connected`}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <SegmentedControl
                ariaLabel="Presentation"
                value={mode}
                onChange={setMode}
                options={[
                  { value: 'visual', label: 'Visual' },
                  { value: 'data', label: 'Data' },
                ]}
              />
              <ExportMenu field={field} dates={dates} states={states} ready={context !== null} />
            </div>
          </div>

          <ul className="mt-8 grid border-y border-line sm:grid-cols-3" aria-label="Source status">
            {SOURCE_ORDER.map(({ key, anchor }, i) => {
              const meta = SOURCE_META[key];
              const part = partOf(key);
              const note = states[key] === 'ok' ? null : (part?.message ?? failureMessage);
              return (
                <li key={key} className={`border-line py-4 sm:px-5 ${i > 0 ? 'border-t sm:border-t-0 sm:border-l' : 'sm:pl-0'}`}>
                  <a href={`#${anchor}`} className="group block rounded-md">
                    <span className="flex items-center gap-2 text-[14px] font-medium text-ink group-hover:underline group-hover:decoration-line-strong group-hover:underline-offset-4">
                      <span className={`h-2 w-2 rounded-full ${meta.dot}`} aria-hidden="true" />
                      {meta.provider}
                    </span>
                    <span className="mt-0.5 block pl-4 text-[13px] text-muted">{meta.purpose}</span>
                    <span className="mt-2 block pl-4">
                      <StatusLabel state={states[key]} />
                    </span>
                    {note && <span className="mt-1 block pl-4 text-[12px] leading-relaxed text-muted">{note}</span>}
                  </a>
                </li>
              );
            })}
          </ul>

          <p className="mt-3 text-[12px] leading-relaxed text-muted">
            Status reflects this field's latest request to the SoilSignal backend (<span className="data">/api/context/all</span>),
            which fetches, normalizes and caches each public source independently.
            {APP_CONFIG.demoMode && ' Demo build: showing a recorded backend response instead of a live request.'}
          </p>

          <div className="mt-12 space-y-16">
            <WeatherPanel part={partOf('weather')} state={states.weather} showData={mode === 'data'} />
            <SoilPanel part={partOf('soil')} state={states.soil} showData={mode === 'data'} />
            <YieldPanel part={partOf('yieldHistory')} state={states.yieldHistory} showData={mode === 'data'} />
          </div>
        </>
      ) : (
        <div className="mt-10" aria-busy="true" aria-label="Loading field">
          <div className="ss-skeleton h-8 w-56 rounded-lg" />
          <div className="ss-skeleton mt-3 h-4 w-72 rounded-md" />
          <div className="ss-skeleton mt-8 h-24 w-full rounded-lg" />
        </div>
      )}
    </div>
  );
}
