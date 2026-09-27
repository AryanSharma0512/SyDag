import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ChevronDown, MapPin } from 'lucide-react';
import type { ImageryAblation, ModelInfo } from '../../types/agricultural';
import type { FinalResults } from '../../types/results';
import type { TrialSite } from '../../types/sites';
import { findSite, getTrialSites, hasForecasts, seasonFor, siteLabel } from '../../services/sites';
import { getFinalResults, maturityFor } from '../../services/results';
import { getImageryAblation, getModels } from '../../services/evaluation';
import { getDatasetLabel } from '../../services/dataset';
import {
  defaultPointIndex,
  getPlotSeries,
  getSitePlots,
  typicalError,
  type PlotOption,
  type PlotSeries,
} from '../../services/plotForecasts';
import { passDates, passesBy } from '../../utils/imagery';
import { formatDay, formatNumber } from '../../utils/formatters';
import { isTypingTarget } from '../../utils/hooks';
import { nearestIndex, toTime } from '../../utils/chart';
import { EASE_OUT } from '../../utils/motion';
import { DashboardSkeleton, ErrorState } from '../common/SkeletonLoader';
import { DebugPanel } from '../debug/DebugPanel';
import { LocationTabs, PlotPicker, SeasonPicker } from './LocationBar';
import { ForecastSummary } from './ForecastSummary';
import { ForecastTimeline } from './ForecastTimeline';
import { HowEarly } from './HowEarly';
import { WeatherOutlookCard } from './WeatherOutlookCard';
import { MaturityCard } from './MaturityCard';
import { SatelliteVsUav } from './SatelliteVsUav';
import { DashboardDetail } from './DashboardDetail';

interface DashboardViewProps {
  isPresentationMode: boolean;
  isDebugMode: boolean;
  onTogglePresentationMode: () => void;
}

const message = (err: unknown) => (err instanceof Error ? err.message : String(err));

/** The first site this deployment can show forecasts for: final results first, then live models. */
function defaultSite(sites: TrialSite[]): TrialSite | undefined {
  return (
    sites.find((s) => (s.forecasts?.finalPlots ?? 0) > 0) ??
    sites.find((s) => s.forecasts?.finalSiteForecast) ??
    sites.find(hasForecasts) ??
    sites[0]
  );
}

function seasonsOf(site: TrialSite): number[] {
  const withForecasts = site.forecasts?.seasons ?? [];
  return withForecasts.length ? withForecasts : site.seasons.map((s) => s.year);
}

/** Keep the dashboard's place in the URL (?site=&plot=) so a view can be shared or reloaded. */
function writeUrl(siteId: string | null, plotId: string | null) {
  const url = new URL(window.location.href);
  if (siteId) url.searchParams.set('site', siteId);
  else url.searchParams.delete('site');
  if (plotId) url.searchParams.set('plot', plotId);
  else url.searchParams.delete('plot');
  if (url.href !== window.location.href) window.history.replaceState(null, '', url);
}

function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-line bg-surface p-5 sm:p-7 ${className}`}>{children}</section>;
}

export function DashboardView({ isPresentationMode, isDebugMode, onTogglePresentationMode }: DashboardViewProps) {
  const initial = useRef(new URLSearchParams(window.location.search));
  const [attempt, setAttempt] = useState(0);

  const [sites, setSites] = useState<TrialSite[] | null>(null);
  const [sitesError, setSitesError] = useState<string | null>(null);
  const [results, setResults] = useState<FinalResults | null>(null);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [resultsSettled, setResultsSettled] = useState(false);

  const [siteId, setSiteId] = useState<string | null>(null);
  const [season, setSeason] = useState<number | null>(null);
  const [plots, setPlots] = useState<PlotOption[] | null>(null);
  const [plotsError, setPlotsError] = useState<string | null>(null);
  const [plotKey, setPlotKey] = useState<string | null>(null);
  const [series, setSeries] = useState<PlotSeries | null>(null);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);

  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [ablation, setAblation] = useState<ImageryAblation | null>(null);
  const [ablationError, setAblationError] = useState<string | null>(null);
  const [datasetLabel, setDatasetLabel] = useState<string | null>(null);
  const [showDetail, setShowDetail] = useState(false);

  const [simulateLoading, setSimulateLoading] = useState(false);
  const [missingSatellite, setMissingSatellite] = useState(false);
  const [weatherError, setWeatherError] = useState(false);

  const activeDateRef = useRef<string | null>(null);
  const resetRef = useRef(false);

  // Sites and the final results decide where to start; results failing never hides the live forecasts.
  useEffect(() => {
    let active = true;
    setSitesError(null);
    getTrialSites()
      .then((list) => active && setSites(list))
      .catch((err: unknown) => active && setSitesError(message(err)));
    getFinalResults()
      .then((r) => active && setResults(r))
      .catch((err: unknown) => active && setResultsError(message(err)))
      .finally(() => active && setResultsSettled(true));
    getModels()
      .then((list) => active && setModels(list))
      .catch((err: unknown) => active && setModelsError(message(err)));
    getImageryAblation()
      .then((a) => active && setAblation(a))
      .catch((err: unknown) => active && setAblationError(message(err)));
    getDatasetLabel()
      .then((label) => active && setDatasetLabel(label))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [attempt]);

  const site = sites ? findSite(sites, siteId) : undefined;

  // First visit: the site in the URL, else the first one with forecasts.
  useEffect(() => {
    if (!sites || siteId) return;
    const chosen = findSite(sites, initial.current.get('site')) ?? defaultSite(sites);
    if (chosen) setSiteId(chosen.id);
  }, [sites, siteId]);

  const seasons = useMemo(() => (site ? seasonsOf(site) : []), [site]);
  // The chosen season if this site has it, else the site's latest; derived, so a new site never sees the old one's.
  const activeSeason = season !== null && seasons.includes(season) ? season : (seasons[seasons.length - 1] ?? null);

  // The site's plots, once the final results have settled (they replace the live models where they cover a site).
  useEffect(() => {
    if (!site || !resultsSettled) return;
    let active = true;
    setPlots(null);
    setPlotsError(null);
    getSitePlots(site, results, activeSeason ?? undefined)
      .then((list) => {
        if (!active) return;
        setPlots(list);
        const wanted = initial.current.get('plot');
        initial.current.delete('plot');
        const chosen =
          (wanted && list.find((p) => p.plotId === wanted || p.fieldId === wanted)) || list.find((p) => p.featured) || list[0];
        setPlotKey(chosen?.key ?? null);
        if (!chosen) setSeries(null);
      })
      .catch((err: unknown) => active && setPlotsError(message(err)));
    return () => {
      active = false;
    };
  }, [site, activeSeason, results, resultsSettled, attempt]);

  const option = plots?.find((p) => p.key === plotKey) ?? null;

  useEffect(() => {
    if (!option || !site) return;
    let active = true;
    setSeriesError(null);
    getPlotSeries(option, site, results)
      .then((next) => {
        if (!active) return;
        let nextIndex = defaultPointIndex(next.points, results, next.source);
        if (resetRef.current) resetRef.current = false;
        else if (activeDateRef.current && series && series.siteId === next.siteId) {
          // Switching plots at the same site keeps the same point in the season.
          nextIndex = nearestIndex(
            next.points.map((p) => toTime(p.date)),
            toTime(activeDateRef.current),
          );
        }
        setSeries(next);
        setIndex(nextIndex);
      })
      .catch((err: unknown) => active && setSeriesError(message(err)));
    return () => {
      active = false;
    };
    // `series` is read only to compare sites; reloading on its change would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [option, site, results]);

  const current = series && series.siteId === site?.id ? series : null;
  const pointIndex = current ? Math.min(index, current.points.length - 1) : 0;
  const point = current?.points[pointIndex];
  useEffect(() => {
    activeDateRef.current = point?.date ?? null;
  }, [point]);

  useEffect(() => {
    if (!site) return;
    writeUrl(site.id, current && !current.isSiteAverage ? current.plotId : null);
  }, [site, current]);

  const selectSite = useCallback((id: string) => {
    setSiteId(id);
    setPlots(null);
    setPlotKey(null);
  }, []);

  const selectLivePlot = useCallback(
    (fieldId: string) => {
      const match = plots?.find((p) => p.fieldId === fieldId);
      if (match) {
        setPlotKey(match.key);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    },
    [plots],
  );

  const reset = useCallback(() => {
    setSimulateLoading(false);
    setMissingSatellite(false);
    setWeatherError(false);
    if (!sites) return;
    const first = defaultSite(sites);
    resetRef.current = true;
    if (first && first.id !== siteId) selectSite(first.id);
    else if (current) setIndex(defaultPointIndex(current.points, results, current.source));
  }, [sites, siteId, current, results, selectSite]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTypingTarget(event.target)) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest('[role="slider"], [role="tablist"], [role="menu"], [role="listbox"], [role="group"]')) return;
      const count = current?.points.length ?? 0;
      const facilitator = isDebugMode || isPresentationMode;
      if (event.key === 'ArrowLeft' && count) {
        event.preventDefault();
        setIndex((i) => Math.max(0, Math.min(i, count - 1) - 1));
      } else if (event.key === 'ArrowRight' && count) {
        event.preventDefault();
        setIndex((i) => Math.min(count - 1, i + 1));
      } else if (facilitator && sites && /^[1-9]$/.test(event.key)) {
        const next = sites[Number(event.key) - 1];
        if (next) selectSite(next.id);
      } else if (facilitator && (event.key === 'r' || event.key === 'R')) {
        event.preventDefault();
        reset();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [current, sites, isDebugMode, isPresentationMode, reset, selectSite]);

  const seasonDomain = useMemo<[number, number]>(() => {
    if (!current) return [0, 1];
    const lo = Math.min(...current.points.map((p) => p.lowerBound ?? p.yield));
    const hi = Math.max(...current.points.map((p) => p.upperBound ?? p.yield));
    return [lo - 6, hi + 6];
  }, [current]);

  // Live plots: the plot's own image dates. Final results: the site's pass calendar, which dates their stages
  // (the inventory's plot-image count does not matter here: the results were modeled on those passes).
  const passes = useMemo(() => {
    if (current?.live) return passDates(current.live);
    const inventory = site?.seasons.find((s) => s.year === current?.season)?.satellite;
    if (current?.source === 'final') return inventory?.acquisitionDates ?? [];
    return inventory && inventory.plotImages > 0 ? inventory.acquisitionDates : [];
  }, [current, site]);
  const error = point && current ? typicalError(current, point, results, models, site?.name) : null;
  const level = current?.source === 'final' && results?.status === 'ready' ? results.interval?.level : null;
  const rangeLabel = level ? `${Math.round(level * 100)}% prediction range` : 'Prediction range';
  const passCount = point && passes.length ? passesBy(passes, point.date) : 0;
  const stageNote =
    current?.source === 'final' && passCount > 0 ? `satellite pass ${passCount} of ${passes.length}` : undefined;
  const liveSnapshot = current?.live?.snapshots[pointIndex];
  const seasonYear = activeSeason ?? current?.season ?? (site ? seasonFor(site, undefined)?.year : undefined);
  const maturity = site && seasonYear ? maturityFor(results, site.id, seasonYear, current?.plotId) : null;
  // Crop development shows only real GDD (live model) or a published maturity window; otherwise it is left out.
  const gdd = liveSnapshot ? { value: liveSnapshot.weather.gddAccumulated, asOf: liveSnapshot.date } : null;
  const showMaturity = !!gdd || !!maturity || !!point?.stage;
  const loadingSeries = !!option && (!current || current.key !== option.key) && !seriesError;

  const heading = isPresentationMode ? 'text-[40px] sm:text-[52px]' : 'text-[32px] sm:text-[42px]';

  return (
    <div className={`mx-auto max-w-6xl px-4 pb-24 sm:px-6 ${isPresentationMode ? 'pt-6' : 'pt-8 sm:pt-10'}`}>
      {sitesError ? (
        <ErrorState
          title="Forecasts are unavailable"
          message={`The SoilSignal API did not respond (${sitesError}). No demo data is shown in its place.`}
          onRetry={() => setAttempt((n) => n + 1)}
        />
      ) : !sites || !site ? (
        <DashboardSkeleton />
      ) : (
        <>
          <LocationTabs sites={sites} selectedId={site.id} onSelect={selectSite} large={isPresentationMode} />

          <header className="mt-7">
            <p
              className={`flex flex-wrap items-center gap-x-3 gap-y-2 font-medium text-leaf-700 ${isPresentationMode ? 'text-[16px]' : 'text-[14px]'}`}
            >
              <span>
                {site.crop}
                {seasonYear ? (
                  <>
                    {' · '}
                    <span className="data">{seasonYear}</span> season
                  </>
                ) : null}
              </span>
              <SeasonPicker seasons={seasons} value={activeSeason ?? 0} onChange={setSeason} />
            </p>
            <h1 className={`mt-1 leading-[1.05] font-semibold tracking-[-0.035em] text-ink ${heading}`}>{siteLabel(site)}</h1>
            {current && !current.isSiteAverage ? (
              <div
                className={`mt-3 flex flex-wrap items-center gap-x-6 gap-y-1 ${isPresentationMode ? 'text-[17px]' : 'text-[15px]'}`}
              >
                <PlotPicker plots={plots ?? []} selectedKey={plotKey} onSelect={setPlotKey} />
                {current.hybrid && (
                  <span className="text-muted">
                    Hybrid <span className="data font-medium text-ink">{current.hybrid}</span>
                  </span>
                )}
                {current.nitrogenLbAc != null && (
                  <span className="text-muted">
                    <span className="data font-medium text-ink">{Math.round(current.nitrogenLbAc)}</span> lb N/ac
                  </span>
                )}
                {current.plantingDate && (
                  <span className="text-muted">
                    Planted <span className="data font-medium text-ink">{formatDay(current.plantingDate)}</span>
                  </span>
                )}
                {current.irrigated !== undefined && (
                  <span className="text-muted">{current.irrigated ? 'Irrigated' : 'Rainfed'}</span>
                )}
              </div>
            ) : current?.isSiteAverage ? (
              <p className="mt-3 text-[15px] text-muted">All plots at this location (site average)</p>
            ) : null}
          </header>

          {plotsError || seriesError ? (
            <div className="mt-8">
              <ErrorState
                title="This forecast is unavailable"
                message={`The SoilSignal API did not return it (${plotsError ?? seriesError}). No demo data is shown in its place.`}
                onRetry={() => setAttempt((n) => n + 1)}
              />
            </div>
          ) : plots && plots.length === 0 ? (
            <NoForecasts site={site} results={results} />
          ) : !current || !point || simulateLoading ? (
            <div className="mt-8">
              <DashboardSkeleton />
            </div>
          ) : (
            <motion.div initial={false} animate={{ opacity: loadingSeries ? 0.45 : 1 }} transition={{ duration: 0.15 }}>
              <div className="mt-8">
                <ForecastSummary
                  point={point}
                  previous={current.points[pointIndex - 1]}
                  seasonDomain={seasonDomain}
                  typicalError={error}
                  rangeLabel={rangeLabel}
                  stageNote={stageNote}
                  isPresentationMode={isPresentationMode}
                />
              </div>

              <p
                className={`mt-12 mb-3 font-medium tracking-[0.08em] text-faint uppercase ${isPresentationMode ? 'text-[13px]' : 'text-[11px]'}`}
              >
                How the forecast developed
              </p>
              <Card>
                <ForecastTimeline
                  fieldKey={current.key}
                  snapshots={current.points}
                  activeIndex={pointIndex}
                  onSelectIndex={setIndex}
                  isPresentationMode={isPresentationMode}
                  passes={passes}
                  plantingDate={current.plantingDate}
                  platform={current.live?.spatial?.satellitePlatform ?? (current.source === 'final' ? 'Pléiades Neo' : undefined)}
                  rangeLabel={rangeLabel}
                />
              </Card>

              <Card className="mt-6">
                <HowEarly
                  results={results}
                  error={resultsError}
                  siteId={site.id}
                  siteName={site.name}
                  season={current.season}
                  activeDap={current.source === 'final' ? point.dap : null}
                  activeStage={current.source === 'final' ? point.validationStage : null}
                  isPresentationMode={isPresentationMode}
                />
              </Card>

              <div className={`mt-6 grid grid-cols-1 items-stretch gap-6 ${showMaturity ? 'lg:grid-cols-2' : ''}`}>
                <Card>
                  <WeatherOutlookCard
                    site={site}
                    asOfDate={point.date}
                    plantingDate={current.plantingDate}
                    isPresentationMode={isPresentationMode}
                  />
                </Card>
                {showMaturity && (
                  <Card>
                    <MaturityCard
                      gdd={gdd}
                      stage={point.stage}
                      stageDetail={point.stageSubtext}
                      maturity={maturity}
                      isPresentationMode={isPresentationMode}
                    />
                  </Card>
                )}
              </div>

              <Card className="mt-6">
                <SatelliteVsUav results={results} plotUav={current.uav} sites={sites} isPresentationMode={isPresentationMode} />
              </Card>

              {!isPresentationMode && (
                <div className="mt-12 border-t border-line pt-6">
                  <button
                    type="button"
                    onClick={() => setShowDetail((v) => !v)}
                    aria-expanded={showDetail}
                    aria-controls="dashboard-detail"
                    className="group flex w-full items-center justify-between gap-4 rounded-xl px-1 py-2 text-left"
                  >
                    <span>
                      <span className="block text-[17px] font-semibold tracking-[-0.01em] text-ink">More detail</span>
                      <span className="mt-0.5 block text-[14px] text-muted">
                        {current.live
                          ? 'Model drivers, crop observations, every plot at this date, model validation, weather and soil, data sources.'
                          : `Validation at ${site.name} by satellite stage, and across all ${results?.plotCounts.length ?? ''} sites.`}
                      </span>
                    </span>
                    <ChevronDown
                      className={`h-5 w-5 shrink-0 text-muted transition-transform duration-200 group-hover:text-ink ${showDetail ? 'rotate-180' : ''}`}
                    />
                  </button>
                  <AnimatePresence initial={false}>
                    {showDetail && (
                      <motion.div
                        id="dashboard-detail"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3, ease: EASE_OUT }}
                        className="overflow-hidden"
                      >
                        <DashboardDetail
                          site={site}
                          season={current.season}
                          activeStage={point.validationStage}
                          live={current.live}
                          snapshotIndex={pointIndex}
                          results={results}
                          models={models}
                          modelsError={modelsError}
                          ablation={ablation}
                          ablationError={ablationError}
                          datasetLabel={datasetLabel}
                          onSelectLivePlot={selectLivePlot}
                          simulateMissingSatellite={missingSatellite}
                          simulateWeatherError={weatherError}
                          onClearWeatherError={() => setWeatherError(false)}
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </motion.div>
          )}
        </>
      )}

      {isDebugMode && sites && (
        <DebugPanel
          sites={sites}
          selectedSiteId={site?.id ?? ''}
          onSelectSite={selectSite}
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

/** A location this deployment has no plot forecasts for: say so, and what data exists there. */
function NoForecasts({ site, results }: { site: TrialSite; results: FinalResults | null }) {
  const season = site.seasons[0];
  const satellite = season?.satellite.plotImages ?? 0;
  const uav = season?.uav.plotImages ?? 0;
  return (
    <section className="mt-8 rounded-2xl border border-dashed border-line-strong bg-surface/60 p-6 sm:p-8">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-mist text-muted">
          <MapPin className="h-4 w-4" aria-hidden="true" />
        </span>
        <div>
          <h2 className="text-[18px] font-semibold tracking-[-0.01em] text-ink">No plot forecasts for {site.name} yet</h2>
          <p className="mt-1 max-w-2xl text-[15px] leading-relaxed text-muted">
            {results?.status === 'ready'
              ? 'The published final results do not include this location.'
              : 'Forecasts for this location appear when the final model results include it.'}{' '}
            {satellite === 0 && season
              ? 'The challenge data has field records here but no usable plot imagery, so a forecast would rest on records and weather alone.'
              : ''}
          </p>
        </div>
      </div>
      {season && (
        <dl className="mt-6 grid grid-cols-2 gap-x-8 gap-y-4 border-t border-line pt-5 text-[14px] sm:grid-cols-4">
          <div>
            <dt className="text-muted">Trial plots, {season.year}</dt>
            <dd className="data mt-0.5 text-[18px] font-medium text-ink">{formatNumber(season.plots)}</dd>
          </div>
          <div>
            <dt className="text-muted">Satellite plot images</dt>
            <dd className="data mt-0.5 text-[18px] font-medium text-ink">{formatNumber(satellite)}</dd>
          </div>
          <div>
            <dt className="text-muted">UAV plot images</dt>
            <dd className="data mt-0.5 text-[18px] font-medium text-ink">{formatNumber(uav)}</dd>
          </div>
          <div>
            <dt className="text-muted">Weather history</dt>
            <dd className="data mt-0.5 text-[18px] font-medium text-ink">
              {site.weather ? `${site.weather.seasons} seasons` : '—'}
            </dd>
          </div>
        </dl>
      )}
    </section>
  );
}
