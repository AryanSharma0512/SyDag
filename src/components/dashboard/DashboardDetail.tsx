import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import type { DataSource, DecisionSet, FieldForecast, ImageryAblation, ModelInfo } from '../../types/agricultural';
import type { FinalResults } from '../../types/results';
import { getDecisions } from '../../services/decisions';
import { getDataSources } from '../../services/sources';
import { passDates } from '../../utils/imagery';
import { formatDay } from '../../utils/formatters';
import { useLocationContext } from '../../utils/useLocationContext';
import { Link } from '../../utils/router';
import { EmptyState, ErrorState } from '../common/SkeletonLoader';
import { PerformanceTable } from '../results/PerformanceByDap';
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

interface DashboardDetailProps {
  /** The live model's forecast for the plot; absent when the final results serve it. */
  live?: FieldForecast;
  snapshotIndex: number;
  results: FinalResults | null;
  models: ModelInfo[] | null;
  modelsError: string | null;
  ablation: ImageryAblation | null;
  ablationError: string | null;
  datasetLabel: string | null;
  onSelectLivePlot: (fieldId: string) => void;
  simulateMissingSatellite: boolean;
  simulateWeatherError: boolean;
  onClearWeatherError: () => void;
}

const DEBOUNCE_MS = 120;

function Heading({ children, note }: { children: string; note?: string }) {
  return (
    <div className="mb-5">
      <h3 className="text-[16px] font-semibold tracking-[-0.01em] text-ink">{children}</h3>
      {note && <p className="mt-1 max-w-2xl text-[13px] text-muted">{note}</p>}
    </div>
  );
}

/**
 * Everything behind "More detail": the research views that support the forecast but
 * should not compete with it. Mounted only when opened, so its data loads on demand.
 */
export function DashboardDetail(props: DashboardDetailProps) {
  const { live, snapshotIndex, results } = props;
  return (
    <div className="space-y-14 pt-8">
      <div className="flex flex-col gap-3 rounded-xl bg-mist/60 px-5 py-4 text-[14px] text-ink-soft sm:flex-row sm:items-center sm:justify-between">
        <span>How the data was processed, how the model was validated, and what every source is.</span>
        <span className="flex gap-5 font-medium">
          <Link to="methodology" className="inline-flex items-center gap-1 text-leaf-700 hover:text-leaf-800">
            Methodology <ArrowRight className="h-3.5 w-3.5" />
          </Link>
          <Link to="data" className="inline-flex items-center gap-1 text-leaf-700 hover:text-leaf-800">
            Data <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </span>
      </div>

      {results?.status === 'ready' && (
        <section>
          <Heading
            note={[
              results.model?.name && `${results.model.name}`,
              results.model?.validation,
              results.resultsVersion && `results ${results.resultsVersion}`,
            ]
              .filter(Boolean)
              .join(' · ')}
          >
            Validation by days after planting
          </Heading>
          <PerformanceTable performance={results.performance} earliestUsefulDap={results.earliestUsefulDap} />
        </section>
      )}

      {live ? (
        <LiveDetail {...props} live={live} snapshotIndex={snapshotIndex} />
      ) : (
        <section>
          <Heading note="The deployed models' own validation, independent of the plot shown above.">Deployed models</Heading>
          <div className="grid grid-cols-1 items-stretch gap-12 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] lg:gap-14">
            <ModelReliability
              models={props.models}
              error={props.modelsError}
              season={results?.plotCounts[0]?.season ?? new Date().getFullYear()}
              activeDate=""
              passes={[]}
              datasetLabel={props.datasetLabel}
            />
            <ImageryValue ablation={props.ablation} error={props.ablationError} season={results?.plotCounts[0]?.season ?? 0} />
          </div>
        </section>
      )}
    </div>
  );
}

function LiveDetail({
  live,
  snapshotIndex,
  models,
  modelsError,
  ablation,
  ablationError,
  datasetLabel,
  onSelectLivePlot,
  simulateMissingSatellite,
  simulateWeatherError,
  onClearWeatherError,
}: DashboardDetailProps & { live: FieldForecast }) {
  const snapshot = live.snapshots[Math.min(snapshotIndex, live.snapshots.length - 1)];
  const field = live.field;
  const passes = useMemo(() => passDates(live), [live]);
  const asOfDate = snapshot.date;

  const [sources, setSources] = useState<DataSource[]>([]);
  useEffect(() => {
    let active = true;
    getDataSources(live).then((list) => active && setSources(list));
    return () => {
      active = false;
    };
  }, [live]);

  // Every plot as of the selected date, so the table never shows a forecast from later on.
  const [decisions, setDecisions] = useState<DecisionSet | null>(null);
  const [decisionsLoading, setDecisionsLoading] = useState(false);
  const [decisionsError, setDecisionsError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const cache = useRef(new Map<string, DecisionSet>());
  useEffect(() => {
    const cached = cache.current.get(asOfDate);
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
          cache.current.set(asOfDate, set);
          setDecisions(set);
          setDecisionsError(null);
        })
        .catch((err: unknown) => !cancelled && setDecisionsError(err instanceof Error ? err.message : String(err)))
        .finally(() => !cancelled && setDecisionsLoading(false));
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [asOfDate, attempt]);

  const forecastDates = useMemo(() => live.snapshots.map((s) => s.date), [live]);
  const context = useLocationContext(field, forecastDates);
  const loaded = context && context.fieldId === field.id ? context : null;
  const unreachable = loaded && !loaded.data ? 'Public data could not be loaded.' : null;
  const soilPart = loaded?.data?.soil;
  const weatherPart = loaded?.data?.weather;
  const yieldPart = loaded?.data?.yieldHistory;

  return (
    <>
      <section>
        <Heading note="How far each input moved this forecast, from the model that made it.">Why this forecast</Heading>
        <ModelExplanation drivers={snapshot.explanations} featureImportance={snapshot.featureImportance} />
      </section>

      <section>
        {simulateMissingSatellite ? (
          <EmptyState
            title="No satellite observations for this period"
            message="Cloud cover or an orbital gap left this window without imagery. Weather and soil context are unaffected."
          />
        ) : (
          <CropDevelopment
            fieldKey={field.id}
            timeline={live.fullVegetationSeries}
            events={live.events}
            activeDate={snapshot.date}
          />
        )}
      </section>

      <section>
        {(live.spatial ?? snapshot.spatial) ? (
          <SpatialFieldView spatial={(live.spatial ?? snapshot.spatial)!} fieldName={field.name} />
        ) : (
          <EmptyState
            title="Nothing to map yet"
            message={`As of ${snapshot.displayDate} there is no satellite image of this plot; the map appears with the first one.`}
          />
        )}
      </section>

      <section>
        <Heading note="Every plot in the trial at this forecast date. Useful for choosing where to scout.">
          Every plot at this date
        </Heading>
        <ScoutingQueue
          decisions={decisions}
          updating={decisionsLoading && decisions !== null}
          error={decisionsError}
          onRetry={() => setAttempt((n) => n + 1)}
          selectedFieldId={field.id}
          onSelectPlot={onSelectLivePlot}
        />
        {decisions && (
          <div className="mt-14">
            <HybridPerformance plots={decisions.plots} asOfLabel={formatDay(decisions.asOfDate)} />
          </div>
        )}
      </section>

      <section>
        <Heading note="Validation of the models deployed on this server, by forecast date.">Deployed models</Heading>
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
      </section>

      <section>
        <Heading note="Observed weather, soil and county yields for this location (NOAA, USDA). Context only.">
          Location context
        </Heading>
        <div className="grid grid-cols-1 items-stretch gap-6 lg:grid-cols-2">
          {simulateWeatherError ? (
            <ErrorState
              title="Weather context is unavailable"
              message="The weather service did not respond. The forecast and crop observations are unaffected."
              onRetry={onClearWeatherError}
            />
          ) : (
            <EnvironmentalContext
              weather={snapshot.weather}
              soil={snapshot.soil}
              asOf={snapshot.date}
              observed={weatherPart?.status === 'ok' ? weatherPart.data : null}
              soilProfile={soilPart?.status === 'ok' ? soilPart.data : null}
              weatherNote={weatherPart?.message ?? unreachable}
              soilNote={soilPart?.message ?? unreachable}
            />
          )}
          <div className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
            <HistoricalComparison
              historical={live.historical}
              currentForecastYield={snapshot.yield}
              seasonYear={field.season}
              countyHistory={yieldPart?.status === 'ok' ? yieldPart.data : null}
              countyNote={yieldPart?.status === 'unavailable' ? yieldPart.message : null}
            />
          </div>
        </div>
      </section>

      <section>
        <DataSources sources={sources} />
      </section>
    </>
  );
}
