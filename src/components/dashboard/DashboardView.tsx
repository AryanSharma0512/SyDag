import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import type { DataSource, FieldForecast, FieldMeta } from '../../types/agricultural';
import { getFields } from '../../services/fields';
import { getForecast } from '../../services/forecasts';
import { getDataSources } from '../../services/sources';
import { APP_CONFIG } from '../../config/appConfig';
import { isTypingTarget } from '../../utils/hooks';
import { nearestIndex, toTime } from '../../utils/chart';
import { DashboardSkeleton, EmptyState, ErrorState } from '../common/SkeletonLoader';
import { Reveal } from '../common/Reveal';
import { DebugPanel } from '../debug/DebugPanel';
import { FieldContext } from './FieldContext';
import { ForecastSummary } from './ForecastSummary';
import { ForecastTimeline } from './ForecastTimeline';
import { GrowthStageRail } from './GrowthStageRail';
import { CropDevelopment } from './CropDevelopment';
import { EnvironmentalContext } from './EnvironmentalContext';
import { SpatialFieldView } from './SpatialFieldView';
import { ModelExplanation } from './ModelExplanation';
import { HistoricalComparison } from './HistoricalComparison';
import { DataSources } from './DataSources';

interface DashboardViewProps {
  isPresentationMode: boolean;
  isDebugMode: boolean;
  onTogglePresentationMode: () => void;
}

/** Field switch choreography: fade out, swap data, let values move, fade back in. */
const FADE_OUT_MS = 150;
const DATA_HOLD_MS = 200;

export function DashboardView({ isPresentationMode, isDebugMode, onTogglePresentationMode }: DashboardViewProps) {
  const reduce = useReducedMotion();
  const [fields, setFields] = useState<FieldMeta[]>([]);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [fieldId, setFieldId] = useState(APP_CONFIG.defaultFieldId);
  const [forecast, setForecast] = useState<FieldForecast | null>(null);
  const [index, setIndex] = useState(APP_CONFIG.defaultDateIndex);
  const [dim, setDim] = useState(false);
  const [showSkeleton, setShowSkeleton] = useState(false);

  const [simulateLoading, setSimulateLoading] = useState(false);
  const [missingSatellite, setMissingSatellite] = useState(false);
  const [weatherError, setWeatherError] = useState(false);

  const forecastRef = useRef<FieldForecast | null>(null);
  const activeDateRef = useRef<string | null>(null);
  const resetPendingRef = useRef(false);
  const reduceRef = useRef(reduce);
  reduceRef.current = reduce;

  useEffect(() => {
    let active = true;
    getFields().then((list) => active && setFields(list));
    getDataSources().then((list) => active && setSources(list));
    const id = window.setTimeout(() => setShowSkeleton(true), 250);
    return () => {
      active = false;
      window.clearTimeout(id);
    };
  }, []);

  // Load the selected field through the service layer. Switching keeps the same point in the season.
  useEffect(() => {
    let cancelled = false;
    const timers: number[] = [];
    const animate = forecastRef.current !== null && !reduceRef.current;
    const started = performance.now();
    if (animate) setDim(true);

    getForecast(fieldId).then((data) => {
      if (cancelled) return;
      const swap = () => {
        if (cancelled) return;
        let nextIndex = Math.min(APP_CONFIG.defaultDateIndex, data.snapshots.length - 1);
        if (resetPendingRef.current) {
          resetPendingRef.current = false;
        } else if (activeDateRef.current) {
          nextIndex = nearestIndex(
            data.snapshots.map((s) => toTime(s.date)),
            toTime(activeDateRef.current),
          );
        }
        forecastRef.current = data;
        setForecast(data);
        setIndex(nextIndex);
        if (animate) timers.push(window.setTimeout(() => !cancelled && setDim(false), DATA_HOLD_MS));
        else setDim(false);
      };
      const elapsed = performance.now() - started;
      if (animate && elapsed < FADE_OUT_MS) timers.push(window.setTimeout(swap, FADE_OUT_MS - elapsed));
      else swap();
    });

    return () => {
      cancelled = true;
      timers.forEach((t) => window.clearTimeout(t));
    };
  }, [fieldId]);

  const snapshotIndex = forecast ? Math.min(index, forecast.snapshots.length - 1) : 0;
  const snapshot = forecast?.snapshots[snapshotIndex];

  useEffect(() => {
    activeDateRef.current = snapshot?.date ?? null;
  }, [snapshot]);

  const reset = useCallback(() => {
    setSimulateLoading(false);
    setMissingSatellite(false);
    setWeatherError(false);
    if (fieldId === APP_CONFIG.defaultFieldId) {
      setIndex(APP_CONFIG.defaultDateIndex);
    } else {
      resetPendingRef.current = true;
      setFieldId(APP_CONFIG.defaultFieldId);
    }
  }, [fieldId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTypingTarget(event.target)) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest('[role="slider"], [role="tablist"], [role="menu"], [role="group"]')) return;
      const count = forecastRef.current?.snapshots.length ?? 0;
      if (!count) return;
      const facilitator = isDebugMode || isPresentationMode;
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        setIndex((i) => Math.max(0, Math.min(i, count - 1) - 1));
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        setIndex((i) => Math.min(count - 1, i + 1));
      } else if (facilitator && /^[1-5]$/.test(event.key)) {
        const next = fields[Number(event.key) - 1];
        if (next) setFieldId(next.id);
      } else if (facilitator && (event.key === 'r' || event.key === 'R')) {
        event.preventDefault();
        reset();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [fields, isDebugMode, isPresentationMode, reset]);

  const seasonDomain = useMemo<[number, number]>(() => {
    if (!forecast) return [0, 1];
    const lo = Math.min(...forecast.snapshots.map((s) => s.lowerBound));
    const hi = Math.max(...forecast.snapshots.map((s) => s.upperBound));
    return [lo - 6, hi + 6];
  }, [forecast]);

  const field = forecast?.field;

  return (
    <div className={`mx-auto max-w-6xl px-4 pb-24 sm:px-6 ${isPresentationMode ? 'pt-6' : 'pt-8 sm:pt-10'}`}>
      <h1 className="sr-only">Yield forecast dashboard</h1>
      {forecast && field && snapshot ? (
        <>
          <FieldContext
            fields={fields.length ? fields : [field]}
            field={field}
            snapshot={snapshot}
            onSelectField={setFieldId}
            isPresentationMode={isPresentationMode}
          />

          <motion.div
            className="mt-8"
            initial={false}
            animate={{ opacity: dim ? 0.4 : 1 }}
            transition={{ duration: FADE_OUT_MS / 1000, ease: 'easeOut' }}
          >
            {simulateLoading ? (
              <DashboardSkeleton />
            ) : (
              <>
                <ForecastSummary snapshot={snapshot} seasonDomain={seasonDomain} isPresentationMode={isPresentationMode} />

                <section className="mt-8 rounded-2xl border border-line bg-surface transition-colors duration-300 hover:border-line-strong p-5 sm:p-7">
                  <ForecastTimeline
                    fieldKey={field.id}
                    snapshots={forecast.snapshots}
                    activeIndex={snapshotIndex}
                    onSelectIndex={setIndex}
                    isPresentationMode={isPresentationMode}
                  />
                  <div className="mt-2 border-t border-line pt-5">
                    <GrowthStageRail stage={snapshot.stage} detail={snapshot.stageSubtext} compact={isPresentationMode} />
                  </div>
                </section>

                <Reveal className="mt-6 grid items-stretch gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
                  {missingSatellite ? (
                    <EmptyState
                      title="No satellite observations for this period"
                      message="Cloud cover or an orbital gap left this window without imagery. Weather and soil context are unaffected."
                    />
                  ) : (
                    <CropDevelopment
                      fieldKey={field.id}
                      timeline={forecast.fullVegetationSeries}
                      events={forecast.events}
                      activeDate={snapshot.date}
                    />
                  )}
                  {weatherError ? (
                    <ErrorState
                      title="Weather context is unavailable"
                      message="The weather service did not respond. The forecast and crop observations are unaffected."
                      onRetry={() => setWeatherError(false)}
                    />
                  ) : (
                    <EnvironmentalContext weather={snapshot.weather} soil={snapshot.soil} />
                  )}
                </Reveal>

                <Reveal className="mt-6">
                  <SpatialFieldView spatial={forecast.spatial ?? snapshot.spatial} fieldName={field.name} />
                </Reveal>

                <Reveal className="mt-16">
                  <ModelExplanation drivers={snapshot.explanations} featureImportance={snapshot.featureImportance} />
                </Reveal>

                <Reveal className="mt-16 grid gap-12 border-t border-line pt-10 lg:grid-cols-2 lg:gap-16">
                  <HistoricalComparison
                    historical={forecast.historical}
                    currentForecastYield={snapshot.yield}
                    seasonYear={field.season}
                  />
                  {!isPresentationMode && <DataSources sources={sources} />}
                </Reveal>
              </>
            )}
          </motion.div>
        </>
      ) : showSkeleton ? (
        <DashboardSkeleton />
      ) : (
        <div className="min-h-[70vh]" />
      )}

      {isDebugMode && fields.length > 0 && (
        <DebugPanel
          fields={fields}
          selectedFieldId={fieldId}
          onSelectField={setFieldId}
          simulateLoading={simulateLoading}
          onToggleLoading={() => setSimulateLoading((v) => !v)}
          simulateMissingSatellite={missingSatellite}
          onToggleMissingSatellite={() => setMissingSatellite((v) => !v)}
          simulateWeatherError={weatherError}
          onToggleWeatherError={() => setWeatherError((v) => !v)}
          onReset={reset}
          isPresentationMode={isPresentationMode}
          onTogglePresentationMode={onTogglePresentationMode}
        />
      )}
    </div>
  );
}
