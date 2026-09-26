import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import type { DataSource, DecisionSet, FieldForecast, FieldMeta, ImageryAblation, ModelInfo } from '../../types/agricultural';
import { getFields, pickDefaultFieldId } from '../../services/fields';
import { getForecast } from '../../services/forecasts';
import { getDataSources } from '../../services/sources';
import { getDecisions } from '../../services/decisions';
import { getImageryAblation, getModels } from '../../services/evaluation';
import { getDatasetLabel } from '../../services/dataset';
import { passDates, plantingDate, satellitePlatform } from '../../utils/imagery';
import { formatDay } from '../../utils/formatters';
import { APP_CONFIG } from '../../config/appConfig';
import { isTypingTarget } from '../../utils/hooks';
import { useLocationContext } from '../../utils/useLocationContext';
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
import { ScoutingQueue } from './ScoutingQueue';
import { HybridPerformance } from './HybridPerformance';
import { ModelReliability } from './ModelReliability';
import { ImageryValue } from './ImageryValue';

interface DashboardViewProps {
  isPresentationMode: boolean;
  isDebugMode: boolean;
  onTogglePresentationMode: () => void;
}

/** Field switch choreography: fade out, swap data, let values move, fade back in. */
const FADE_OUT_MS = 150;
const DATA_HOLD_MS = 200;
/** Scrubbing through dates requests the plot list only where the user pauses. */
const DECISIONS_DEBOUNCE_MS = 120;

const message = (err: unknown) => (err instanceof Error ? err.message : String(err));

function SectionLabel({ children }: { children: string }) {
  return <p className="mb-4 text-[11px] font-medium tracking-[0.08em] text-faint uppercase">{children}</p>;
}

export function DashboardView({ isPresentationMode, isDebugMode, onTogglePresentationMode }: DashboardViewProps) {
  const reduce = useReducedMotion();
  const [fields, setFields] = useState<FieldMeta[]>([]);
  const [sources, setSources] = useState<DataSource[]>([]);
  // Chosen once the field list loads: the configured default if this dataset has it.
  const [defaultFieldId, setDefaultFieldId] = useState<string | null>(null);
  const [fieldId, setFieldId] = useState<string | null>(null);
  // A failed API call is shown as an error; the dashboard never falls back to demo data.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [forecast, setForecast] = useState<FieldForecast | null>(null);
  const [index, setIndex] = useState(APP_CONFIG.defaultDateIndex);
  const [dim, setDim] = useState(false);
  const [showSkeleton, setShowSkeleton] = useState(false);

  const [decisions, setDecisions] = useState<DecisionSet | null>(null);
  const [decisionsLoading, setDecisionsLoading] = useState(false);
  const [decisionsError, setDecisionsError] = useState<string | null>(null);
  const [decisionsAttempt, setDecisionsAttempt] = useState(0);
  const decisionCache = useRef(new Map<string, DecisionSet>());
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [ablation, setAblation] = useState<ImageryAblation | null>(null);
  const [ablationError, setAblationError] = useState<string | null>(null);
  const [datasetLabel, setDatasetLabel] = useState<string | null>(null);
  const headerRef = useRef<HTMLDivElement>(null);

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
    getFields()
      .then((list) => {
        if (!active) return;
        const id = pickDefaultFieldId(list);
        if (!id) throw new Error('The forecast service returned no fields.');
        setFields(list);
        setDefaultFieldId(id);
        setFieldId((current) => current ?? id);
      })
      .catch((err: unknown) => active && setLoadError(err instanceof Error ? err.message : String(err)));
    const id = window.setTimeout(() => setShowSkeleton(true), 250);
    return () => {
      active = false;
      window.clearTimeout(id);
    };
  }, [attempt]);

  // Load the selected field through the service layer. Switching keeps the same point in the season.
  useEffect(() => {
    if (!fieldId) return;
    let cancelled = false;
    const timers: number[] = [];
    const animate = forecastRef.current !== null && !reduceRef.current;
    const started = performance.now();
    if (animate) setDim(true);

    getForecast(fieldId)
      .then((data) => {
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
      getDataSources(data).then((list) => !cancelled && setSources(list));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setDim(false);
        setLoadError(err instanceof Error ? err.message : String(err));
      });

    return () => {
      cancelled = true;
      timers.forEach((t) => window.clearTimeout(t));
    };
  }, [fieldId, attempt]);

  // Public data (soil, observed weather, county yields) for every forecast date of the loaded field.
  const forecastDates = useMemo(() => forecast?.snapshots.map((s) => s.date) ?? [], [forecast]);
  const context = useLocationContext(forecast?.field ?? null, forecastDates);

  const snapshotIndex = forecast ? Math.min(index, forecast.snapshots.length - 1) : 0;
  const snapshot = forecast?.snapshots[snapshotIndex];
  const asOfDate = snapshot?.date ?? null;

  useEffect(() => {
    activeDateRef.current = snapshot?.date ?? null;
  }, [snapshot]);

  // Every plot as of the selected date, so the queue never shows a forecast from later on.
  useEffect(() => {
    if (!asOfDate) return;
    const cached = decisionCache.current.get(asOfDate);
    if (cached) {
      setDecisions(cached);
      setDecisionsError(null);
      setDecisionsLoading(false);
      return;
    }
    let cancelled = false;
    setDecisionsLoading(true);
    const timer = window.setTimeout(() => {
      getDecisions(asOfDate)
        .then((set) => {
          if (cancelled) return;
          decisionCache.current.set(asOfDate, set);
          setDecisions(set);
          setDecisionsError(null);
        })
        .catch((err: unknown) => !cancelled && setDecisionsError(message(err)))
        .finally(() => !cancelled && setDecisionsLoading(false));
    }, DECISIONS_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [asOfDate, decisionsAttempt]);

  // Validation results and the imagery comparison describe the models, not a plot: load once.
  useEffect(() => {
    let active = true;
    getModels()
      .then((list) => active && setModels(list))
      .catch((err: unknown) => active && setModelsError(message(err)));
    getImageryAblation()
      .then((result) => active && setAblation(result))
      .catch((err: unknown) => active && setAblationError(message(err)));
    getDatasetLabel()
      .then((label) => active && setDatasetLabel(label))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const selectPlot = useCallback((id: string) => {
    setFieldId(id);
    // The forecast for the new plot is above the queue; bring it into view if it is scrolled away.
    const top = headerRef.current?.getBoundingClientRect().top ?? 0;
    if (top < 0) headerRef.current?.scrollIntoView({ behavior: reduceRef.current ? 'auto' : 'smooth', block: 'start' });
  }, []);

  const reset = useCallback(() => {
    setSimulateLoading(false);
    setMissingSatellite(false);
    setWeatherError(false);
    if (!defaultFieldId || fieldId === defaultFieldId) {
      setIndex(APP_CONFIG.defaultDateIndex);
    } else {
      resetPendingRef.current = true;
      setFieldId(defaultFieldId);
    }
  }, [fieldId, defaultFieldId]);

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
  const passes = useMemo(() => (forecast ? passDates(forecast) : []), [forecast]);
  // Plots opened from the queue are not all in the featured list; keep the open one selectable.
  const selectorFields = field ? (fields.some((f) => f.id === field.id) ? fields : [field, ...fields]) : fields;

  // Each source is used only when it loaded; otherwise panels keep the demo values and say why.
  const live = context && field && context.fieldId === field.id ? context : null;
  const unreachable = live && !live.data ? 'Public data could not be loaded.' : null;
  const soilPart = live?.data?.soil;
  const weatherPart = live?.data?.weather;
  const yieldPart = live?.data?.yieldHistory;
  const soilProfile = soilPart?.status === 'ok' ? soilPart.data : null;
  const observedWeather = weatherPart?.status === 'ok' ? weatherPart.data : null;
  const countyHistory = yieldPart?.status === 'ok' ? yieldPart.data : null;
  const soilLabel = soilProfile
    ? `${soilProfile.series} ${soilProfile.texture ? soilProfile.texture.toLowerCase() : 'soil'}`
    : undefined;

  return (
    <div className={`mx-auto max-w-6xl px-4 pb-24 sm:px-6 ${isPresentationMode ? 'pt-6' : 'pt-8 sm:pt-10'}`}>
      <h1 className="sr-only">Yield forecast dashboard</h1>
      {loadError ? (
        <ErrorState
          title="Forecasts are unavailable"
          message={`The SoilSignal API did not return forecasts (${loadError}). No demo data is shown in their place.`}
          onRetry={() => {
            setLoadError(null);
            setAttempt((n) => n + 1);
          }}
        />
      ) : forecast && field && snapshot ? (
        <>
          <div ref={headerRef} className="scroll-mt-24">
            <FieldContext
              fields={selectorFields}
              field={field}
              snapshot={snapshot}
              onSelectField={setFieldId}
              isPresentationMode={isPresentationMode}
              soilLabel={soilLabel}
            />
          </div>

          <motion.div
            className="mt-8"
            initial={false}
            animate={{ opacity: dim ? 0.4 : 1 }}
            transition={{ duration: FADE_OUT_MS / 1000, ease: 'easeOut' }}
          >
            {simulateLoading ? (
              <DashboardSkeleton />
            ) : (
              <ForecastSummary
                snapshot={snapshot}
                previous={forecast.snapshots[snapshotIndex - 1]}
                seasonDomain={seasonDomain}
                isPresentationMode={isPresentationMode}
              />
            )}
          </motion.div>

          <div className="mt-14">
            <ScoutingQueue
              decisions={decisions}
              updating={decisionsLoading && decisions !== null}
              error={decisionsError}
              onRetry={() => setDecisionsAttempt((n) => n + 1)}
              selectedFieldId={field.id}
              onSelectPlot={selectPlot}
            />
          </div>

          {!simulateLoading && (
            <motion.div
              initial={false}
              animate={{ opacity: dim ? 0.4 : 1 }}
              transition={{ duration: FADE_OUT_MS / 1000, ease: 'easeOut' }}
            >
              <section className="mt-14 rounded-2xl border border-line bg-surface p-5 transition-colors duration-300 hover:border-line-strong sm:p-7">
                <ForecastTimeline
                  fieldKey={field.id}
                  snapshots={forecast.snapshots}
                  activeIndex={snapshotIndex}
                  onSelectIndex={setIndex}
                  isPresentationMode={isPresentationMode}
                  passes={passes}
                  plantingDate={plantingDate(forecast)}
                  platform={satellitePlatform(forecast)}
                />
                <div className="mt-2 border-t border-line pt-5">
                  <GrowthStageRail stage={snapshot.stage} detail={snapshot.stageSubtext} compact={isPresentationMode} />
                </div>
              </section>

              <Reveal className="mt-6">
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
              </Reveal>

              <Reveal className="mt-6">
                {(forecast.spatial ?? snapshot.spatial) ? (
                  <SpatialFieldView spatial={(forecast.spatial ?? snapshot.spatial)!} fieldName={field.name} />
                ) : (
                  <EmptyState
                    title="Nothing to map yet"
                    message={`As of ${snapshot.displayDate} there is no satellite image of this plot; the map appears with the first one.`}
                  />
                )}
              </Reveal>

              <Reveal className="mt-16">
                <ModelExplanation drivers={snapshot.explanations} featureImportance={snapshot.featureImportance} />
              </Reveal>

              {decisions && (
                <Reveal className="mt-16 empty:hidden">
                  <HybridPerformance plots={decisions.plots} asOfLabel={formatDay(decisions.asOfDate)} />
                </Reveal>
              )}

              <Reveal className="mt-16 border-t border-line pt-10">
                <SectionLabel>Model reliability</SectionLabel>
                <div className="grid grid-cols-1 items-stretch gap-12 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] lg:gap-14">
                  <ModelReliability
                    models={models}
                    error={modelsError}
                    season={field.season}
                    activeDate={snapshot.date}
                    passes={passes}
                    datasetLabel={datasetLabel}
                  />
                  <ImageryValue ablation={ablation} error={ablationError} season={field.season} />
                </div>
              </Reveal>

              <Reveal className="mt-16 border-t border-line pt-10">
                <SectionLabel>Environmental context · NOAA and USDA</SectionLabel>
                <div className="grid grid-cols-1 items-stretch gap-6 lg:grid-cols-2">
                  {weatherError ? (
                    <ErrorState
                      title="Weather context is unavailable"
                      message="The weather service did not respond. The forecast and crop observations are unaffected."
                      onRetry={() => setWeatherError(false)}
                    />
                  ) : (
                    <EnvironmentalContext
                      weather={snapshot.weather}
                      soil={snapshot.soil}
                      asOf={snapshot.date}
                      observed={observedWeather}
                      soilProfile={soilProfile}
                      weatherNote={weatherPart?.message ?? unreachable}
                      soilNote={soilPart?.message ?? unreachable}
                    />
                  )}
                  <div className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
                    <HistoricalComparison
                      historical={forecast.historical}
                      currentForecastYield={snapshot.yield}
                      seasonYear={field.season}
                      countyHistory={countyHistory}
                      countyNote={yieldPart?.status === 'unavailable' ? yieldPart.message : null}
                    />
                  </div>
                </div>
              </Reveal>

              {!isPresentationMode && (
                <Reveal className="mt-16 border-t border-line pt-10">
                  <DataSources sources={sources} />
                </Reveal>
              )}
            </motion.div>
          )}
        </>
      ) : showSkeleton ? (
        <DashboardSkeleton />
      ) : (
        <div className="min-h-[70vh]" />
      )}

      {isDebugMode && fields.length > 0 && (
        <DebugPanel
          fields={fields}
          selectedFieldId={fieldId ?? ''}
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
