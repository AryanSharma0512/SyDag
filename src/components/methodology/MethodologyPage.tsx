import { useEffect, useState, type ReactNode } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight, Hourglass, ShieldCheck } from 'lucide-react';
import type { DataSource, FieldForecast, ModelInfo } from '../../types/agricultural';
import type { FinalResults } from '../../types/results';
import type { TrialSite } from '../../types/sites';
import { getForecast } from '../../services/forecasts';
import { getFields, pickDefaultFieldId } from '../../services/fields';
import { getDataSources } from '../../services/sources';
import { getModels } from '../../services/evaluation';
import { getFinalResults, stageForDap } from '../../services/results';
import { getTrialSites, isMappable } from '../../services/sites';
import { EASE_OUT } from '../../utils/motion';
import { formatDay } from '../../utils/formatters';
import { Link } from '../../utils/router';
import { Reveal } from '../common/Reveal';
import { DataBadge } from '../common/DataBadge';
import { PerformanceByDap, PerformanceTable } from '../results/PerformanceByDap';
import { MethodPipeline } from './MethodPipeline';
import { UncertaintyDemo } from './UncertaintyDemo';

const SOURCE_BADGE: Record<DataSource['role'], string> = {
  challenge: 'Challenge',
  practice: 'Practice data',
  public: 'Connected',
  model: 'Model-derived',
  candidate: 'Candidate',
};

const ALGORITHMS: Record<string, string> = {
  RandomForestRegressor: 'Random Forest',
  CatBoostRegressor: 'CatBoost',
  HistGradientBoostingRegressor: 'Gradient boosting',
  LGBMRegressor: 'LightGBM',
  XGBRegressor: 'XGBoost',
  Ridge: 'Ridge regression',
};

const BANDS = [
  { band: 'Red', range: '0.618–0.689 µm', role: 'Absorbed by chlorophyll; low over healthy canopy' },
  { band: 'Green', range: '0.533–0.590 µm', role: 'Chlorophyll reflectance peak' },
  { band: 'Blue', range: '0.446–0.520 µm', role: 'Soil and atmosphere correction (EVI)' },
  { band: 'NIR', range: '0.768–0.888 µm', role: 'Strongly reflected by leaf structure; tracks biomass' },
  { band: 'Red Edge', range: '0.696–0.749 µm', role: 'Sensitive to chlorophyll in dense canopy (NDRE)' },
  { band: 'Deep Blue', range: '0.416–0.456 µm', role: 'Atmospheric and water signal' },
];

const INDICES = [
  { name: 'NDVI', formula: '(NIR − Red) / (NIR + Red)' },
  { name: 'NDRE', formula: '(NIR − Red Edge) / (NIR + Red Edge)' },
  { name: 'GNDVI', formula: '(NIR − Green) / (NIR + Green)' },
  { name: 'EVI', formula: '2.5 (NIR − Red) / (NIR + 6 Red − 7.5 Blue + 1)' },
];

const REPORT_URL = 'https://github.com/AryanSharma0512/SyDag/blob/main/ml/research/weather_outlook.md';

const SECTIONS = [
  ['pipeline', 'Pipeline'],
  ['satellite', 'Satellite processing'],
  ['validation', 'Validation'],
  ['metrics', 'R² and MAE'],
  ['ranges', 'Prediction ranges'],
  ['weather', 'Weather outlook'],
  ['gdd', 'GDD and maturity'],
  ['uav', 'Satellite vs UAV'],
  ['leakage', 'Leakage safeguards'],
  ['sources', 'Data sources'],
] as const;

function Section({ id, title, lead, children }: { id: string; title: string; lead?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 border-t border-line pt-12" aria-labelledby={`${id}-heading`}>
      <Reveal>
        <h2 id={`${id}-heading`} className="text-[24px] font-semibold tracking-[-0.02em] text-ink">
          {title}
        </h2>
        {lead && <div className="mt-2 max-w-3xl text-[15px] leading-relaxed text-muted">{lead}</div>}
      </Reveal>
      <div className="mt-8">{children}</div>
    </section>
  );
}

function Pending({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-dashed border-line-strong px-5 py-5">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-mist text-muted">
        <Hourglass className="h-4 w-4" aria-hidden="true" />
      </span>
      <p className="max-w-2xl text-[14px] leading-relaxed text-muted">{children}</p>
    </div>
  );
}

const pct = (v: number) => `${Math.round(v * 100)}%`;

export function MethodologyPage() {
  const reduce = useReducedMotion();
  const [forecast, setForecast] = useState<FieldForecast | null>(null);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [results, setResults] = useState<FinalResults | null>(null);
  const [sites, setSites] = useState<TrialSite[]>([]);

  useEffect(() => {
    let active = true;
    getFields()
      .then((fields) => {
        const id = pickDefaultFieldId(fields);
        return id ? getForecast(id) : null;
      })
      .then((data) => {
        if (!active || !data) return;
        setForecast(data);
        return getDataSources(data).then((list) => active && setSources(list));
      })
      .catch(() => active && setSources([]));
    getModels()
      .then((list) => active && setModels(list))
      .catch(() => undefined);
    getFinalResults()
      .then((r) => active && setResults(r))
      .catch(() => undefined);
    getTrialSites()
      .then((list) => active && setSites(list.filter(isMappable)))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const ready = results?.status === 'ready';
  const deployed = [...models].filter((m) => m.asOf).sort((a, b) => (a.asOf ?? '').localeCompare(b.asOf ?? ''));
  const algorithms = [...new Set(deployed.map((m) => ALGORITHMS[m.algorithm] ?? m.algorithm))];
  const modelLabel =
    ready && results.model ? results.model.name : algorithms.length ? algorithms.join(' / ') : 'Regression model';
  const modelDetail = ready && results.model ? results.model.validation : 'One model per forecast date';
  const useful = ready && results.earliestUsefulDap != null ? stageForDap(results.performance, results.earliestUsefulDap) : null;
  const holdoutGroup = deployed.find((m) => m.holdout)?.holdout?.group.replace(/^site:\s*/i, '');
  const weatherSites = sites.filter((s) => s.weather);
  const analogSites = weatherSites.filter((s) => s.weather!.analogWeighting);
  const seasonCounts = weatherSites.map((s) => s.weather!.seasons);
  const uavSites = sites.filter((s) => s.seasons.some((x) => x.uav.plotImages > 0));
  const uav = ready ? results.uav : null;

  return (
    <div className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
      <header className="pt-14 pb-10 sm:pt-20 sm:pb-12">
        <motion.p
          className="text-[13px] font-medium text-leaf-700"
          initial={reduce ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: EASE_OUT }}
        >
          Methodology
        </motion.p>
        <motion.h1
          className="mt-3 text-[40px] leading-[1.05] font-semibold tracking-[-0.035em] text-ink sm:text-[54px]"
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE_OUT, delay: 0.05 }}
        >
          How SoilSignal works
        </motion.h1>
        <motion.p
          className="mt-5 max-w-2xl text-[17px] leading-relaxed text-pretty text-muted sm:text-[18px]"
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE_OUT, delay: 0.12 }}
        >
          For each plot, satellite imagery is reduced to plot-level features, combined with the field record and weather, and a
          model estimates final yield with a prediction range. This page shows what went in, how it was validated, and what the
          numbers mean.
        </motion.p>
        <motion.div
          className="mt-6 inline-flex items-center gap-2.5 rounded-full border border-leaf-200 bg-leaf-50 px-4 py-2 text-[15px] font-medium text-leaf-800"
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE_OUT, delay: 0.18 }}
        >
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          Every forecast uses only data that would have been available on that date.
        </motion.div>
        <nav aria-label="On this page" className="mt-10 flex flex-wrap gap-x-5 gap-y-2 text-[14px]">
          {SECTIONS.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="text-muted hover:text-ink">
              {label}
            </a>
          ))}
        </nav>
      </header>

      <div className="space-y-20">
        <Section
          id="pipeline"
          title="From plot imagery to a yield forecast"
          lead="Imagery is the base layer. Field records and weather add context. One model turns the combined features into a final-yield forecast for each date in the season."
        >
          <MethodPipeline modelLabel={modelLabel} modelDetail={modelDetail} />
        </Section>

        <Section
          id="satellite"
          title="Satellite processing"
          lead="Each plot image is a GeoTIFF from Pléiades Neo with six spectral bands, clipped to the plot polygon and zero-filled outside it."
        >
          <div className="grid gap-10 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[440px] text-left">
                <caption className="sr-only">The six spectral bands</caption>
                <thead>
                  <tr className="border-b border-line-strong text-[13px] text-muted">
                    <th scope="col" className="py-2.5 pr-4 font-medium">
                      Band (file order)
                    </th>
                    <th scope="col" className="py-2.5 pr-4 font-medium">
                      Wavelength
                    </th>
                    <th scope="col" className="py-2.5 font-medium">
                      What it shows
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {BANDS.map((b, i) => (
                    <tr key={b.band} className="border-b border-line text-[14px]">
                      <td className="py-2.5 pr-4 font-medium text-ink">
                        <span className="data mr-2 text-faint">{i + 1}</span>
                        {b.band}
                      </td>
                      <td className="data py-2.5 pr-4 text-ink-soft">{b.range}</td>
                      <td className="py-2.5 text-ink-soft">{b.role}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="space-y-5 text-[14px] leading-relaxed text-ink-soft">
              <div>
                <h3 className="font-semibold text-ink">1. Mask the plot pixels</h3>
                <p className="mt-1">
                  Pixels where every band is zero are padding outside the plot and are removed. Pixels with a non-finite, zero or
                  out-of-range band inside the plot are flagged invalid. Every statistic uses valid plot pixels only; the core
                  statistics also drop the outermost ring of pixels, where alleys and neighbouring plots bleed in.
                </p>
              </div>
              <div>
                <h3 className="font-semibold text-ink">2. Compute plot features</h3>
                <p className="mt-1">
                  Band reflectance and vegetation indices are computed per pixel, then summarized per plot (mean, median, spread,
                  percentiles, canopy cover). Across passes, features describe the latest image and how it changed since the
                  previous one.
                </p>
                <ul className="mt-3 space-y-1">
                  {INDICES.map((ix) => (
                    <li key={ix.name} className="flex gap-3">
                      <span className="w-14 shrink-0 font-medium text-ink">{ix.name}</span>
                      <span className="data text-[13px] text-muted">{ix.formula}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </Section>

        <Section
          id="validation"
          title="Validation"
          lead={
            ready ? (
              <>
                {results.model?.name} validated by {results.model?.validation}. Each stage uses only the imagery available by that
                many days after planting.{results.resultsVersion ? ` Results version ${results.resultsVersion}.` : ''}
              </>
            ) : (
              'Validation error by days after planting, from the frozen final run. Plots are validated on data the model did not see during training.'
            )
          }
        >
          {ready && results.performance.length > 0 ? (
            <div className="space-y-8">
              <div className="rounded-2xl border border-line bg-surface p-5 sm:p-7">
                <PerformanceByDap performance={results.performance} earliestUsefulDap={results.earliestUsefulDap} />
              </div>
              <PerformanceTable performance={results.performance} earliestUsefulDap={results.earliestUsefulDap} />
              {results.earliestUsefulRule && (
                <p className="max-w-3xl text-[14px] text-muted">
                  <span className="font-medium text-ink-soft">Earliest useful stage:</span> {results.earliestUsefulRule}
                </p>
              )}
            </div>
          ) : (
            <Pending>
              The final run's validation by days after planting (R², MAE, RMSE) and the earliest useful stage appear here when the
              frozen results are published. Interim numbers are not presented as the result.
            </Pending>
          )}

          {deployed.length > 0 && (
            <details className="group mt-10 rounded-xl border border-line bg-surface">
              <summary className="cursor-pointer list-none px-5 py-4 text-[15px] font-medium text-ink marker:hidden">
                Models currently deployed on this server
                <span className="ml-2 text-[13px] font-normal text-muted">
                  {deployed[0].dataset ?? 'practice data'}
                  {holdoutGroup ? `, held-out site ${holdoutGroup}` : ''}
                </span>
              </summary>
              <div className="overflow-x-auto border-t border-line px-5 pb-5">
                <table className="mt-3 w-full min-w-[640px] text-left">
                  <thead>
                    <tr className="border-b border-line-strong text-[13px] text-muted">
                      <th scope="col" className="py-2.5 pr-4 font-medium">
                        Cutoff
                      </th>
                      <th scope="col" className="py-2.5 pr-4 font-medium">
                        Algorithm
                      </th>
                      <th scope="col" className="py-2.5 pr-4 text-right font-medium">
                        CV MAE
                      </th>
                      <th scope="col" className="py-2.5 pr-4 text-right font-medium">
                        Held-out MAE
                      </th>
                      <th scope="col" className="py-2.5 pr-4 text-right font-medium">
                        Held-out R²
                      </th>
                      <th scope="col" className="py-2.5 text-right font-medium">
                        Yields inside range
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {deployed.map((m) => (
                      <tr key={m.modelId} className="border-b border-line text-[14px]">
                        <td className="data py-2.5 pr-4 text-ink">{m.asOf}</td>
                        <td className="py-2.5 pr-4 text-ink-soft">{ALGORITHMS[m.algorithm] ?? m.algorithm}</td>
                        <td className="data py-2.5 pr-4 text-right text-ink-soft">{m.mae.toFixed(1)}</td>
                        <td className="data py-2.5 pr-4 text-right text-ink-soft">
                          {m.holdout ? m.holdout.mae.toFixed(1) : '—'}
                        </td>
                        <td className="data py-2.5 pr-4 text-right text-ink-soft">{m.holdout ? m.holdout.r2.toFixed(2) : '—'}</td>
                        <td className="data py-2.5 text-right text-ink-soft">
                          {m.holdout ? pct(m.holdout.intervalCoverage) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-3 text-[13px] text-muted">{deployed[0].validation}. MAE in bu/ac.</p>
              </div>
            </details>
          )}
        </Section>

        <Section id="metrics" title="What R² and MAE mean">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="rounded-2xl border border-line bg-surface p-6">
              <h3 className="text-[17px] font-semibold text-ink">MAE: typical error</h3>
              <p className="mt-2 text-[14px] leading-relaxed text-ink-soft">
                Mean absolute error: how far the forecast was from the harvested yield, on average, in bushels per acre. For
                example, an MAE of 12 means a typical forecast missed by about 12 bu/ac. This is the number the forecast page
                shows as “typical validation error”.
              </p>
            </div>
            <div className="rounded-2xl border border-line bg-surface p-6">
              <h3 className="text-[17px] font-semibold text-ink">R²: variation explained</h3>
              <p className="mt-2 text-[14px] leading-relaxed text-ink-soft">
                The share of the plot-to-plot differences in final yield that the model accounts for. 1 is perfect; 0 is no better
                than predicting the average for every plot; below 0 is worse than that. R² is not an accuracy percentage and not a
                confidence level.
              </p>
              {useful?.r2 != null && (
                <p className="mt-3 border-t border-line pt-3 text-[14px] leading-relaxed text-ink">
                  At <span className="data">{useful.dap}</span> days after planting, the model explained about{' '}
                  <span className="data font-medium">{Math.round(useful.r2 * 100)}%</span> of the observed variation in final
                  yield in this validation.
                </p>
              )}
            </div>
          </div>
        </Section>

        <Section
          id="ranges"
          title="Prediction ranges"
          lead={
            ready && results.interval?.coverage != null ? (
              <>
                Each forecast carries a range set from validation errors
                {results.interval.method ? ` (${results.interval.method})` : ''}. In validation,{' '}
                <span className="data text-ink">{pct(results.interval.coverage)}</span> of final yields fell inside it
                {results.interval.level ? `, against a target of ${pct(results.interval.level)}` : ''}. Treat it as an uncertainty
                range, not a guarantee.
              </>
            ) : (
              'Each forecast carries a range set from the model’s validation errors. How often final yields fall inside it can shift from site to site, so the range is an uncertainty band, not a guarantee. Coverage on the held-out site is listed with the deployed models above.'
            )
          }
        >
          <Reveal className="rounded-2xl border border-line bg-surface p-5 sm:p-8">
            {forecast ? <UncertaintyDemo forecast={forecast} /> : <div className="h-[320px]" />}
          </Reveal>
        </Section>

        <Section
          id="weather"
          title="Historical weather outlook"
          lead={
            <>
              What kinds of weather followed this point in past seasons? For each site SoilSignal keeps{' '}
              {seasonCounts.length ? `${Math.min(...seasonCounts)}–${Math.max(...seasonCounts)}` : 'several decades of'}{' '}
              quality-checked seasons of NOAA GHCN-Daily station records, and reads off what the next 30, 60 or 90 days, or the
              rest of the season, brought in each of them. It is not a weather forecast.
            </>
          }
        >
          <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
            <div className="space-y-4 text-[14px] leading-relaxed text-ink-soft">
              <p>
                Each past season's weather after the forecast date is scored for maize (water supply at rainfed sites, heat at the
                irrigated site) and sorted into adverse, typical and favorable thirds. The outlook reports how many past seasons
                fell into each, with the rain, heat and growing degree days they brought.
              </p>
              <p>
                <span className="font-medium text-ink">Similar seasons were tested, not assumed.</span> We tested whether seasons
                that looked similar so far were better predictors of what happened next. At most rainfed sites they were not, so
                SoilSignal falls back to the historical distribution rather than pretending the additional complexity helps.
                {analogSites.length > 0 &&
                  ` At ${analogSites.map((x) => x.name).join(' and ')}, similar-season weighting showed some additional skill for heat-related conditions and is used there.`}
              </p>
              <p>
                The outlook and the yield forecast are shown separately. The interface for running each historical weather
                scenario through the yield model exists, but the yield model does not yet use future-weather features, so no
                yield-per-scenario numbers are shown.
              </p>
              <a
                href={REPORT_URL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 font-medium text-leaf-700 hover:text-leaf-800"
              >
                Research report and backtest <ArrowRight className="h-3.5 w-3.5" />
              </a>
            </div>
            {weatherSites.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[480px] text-left">
                  <caption className="sr-only">Weather history by site</caption>
                  <thead>
                    <tr className="border-b border-line-strong text-[13px] text-muted">
                      <th scope="col" className="py-2.5 pr-4 font-medium">
                        Site
                      </th>
                      <th scope="col" className="py-2.5 pr-4 font-medium">
                        Station
                      </th>
                      <th scope="col" className="py-2.5 pr-4 text-right font-medium">
                        Seasons
                      </th>
                      <th scope="col" className="py-2.5 font-medium">
                        Past seasons weighted
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {weatherSites.map((s) => (
                      <tr key={s.id} className="border-b border-line text-[14px]">
                        <td className="py-2.5 pr-4 font-medium text-ink">{s.name}</td>
                        <td className="py-2.5 pr-4 text-ink-soft">{s.weather!.station ?? '—'}</td>
                        <td className="data py-2.5 pr-4 text-right text-ink-soft">
                          {s.weather!.seasons}
                          <span className="ml-1 text-[12px] text-faint">
                            {s.weather!.firstSeason}–{s.weather!.lastSeason}
                          </span>
                        </td>
                        <td className="py-2.5 text-ink-soft">
                          {s.weather!.analogWeighting ? 'By similarity so far' : 'Equally (climatology)'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Section>

        <Section
          id="gdd"
          title="Growing degree days and maturity"
          lead="Maize development follows accumulated heat, not the calendar. Each day adds growing degree days (GDD) from the daily high and low, counted from planting."
        >
          <div className="grid gap-6 md:grid-cols-2">
            <div className="rounded-2xl border border-line bg-surface p-6 text-[14px] leading-relaxed text-ink-soft">
              <p className="data text-[15px] text-ink">GDD = (min(max(Tmax, 50), 86) + min(max(Tmin, 50), 86)) / 2 − 50</p>
              <p className="mt-3">
                The 86/50 °F method: temperatures are capped at 86 °F and floored at 50 °F, because maize barely develops below 50
                °F and does not speed up above 86 °F. The same formula builds the model's weather features and the outlook.
              </p>
            </div>
            <div className="rounded-2xl border border-line bg-surface p-6 text-[14px] leading-relaxed text-ink-soft">
              <h3 className="text-[16px] font-semibold text-ink">Estimated maturity window</h3>
              {ready && results.maturity.some((m) => m.method) ? (
                <p className="mt-2">{results.maturity.find((m) => m.method)!.method}</p>
              ) : ready && results.maturity.length > 0 ? (
                <p className="mt-2">
                  The final results give a physiological-maturity window for{' '}
                  {[...new Set(results.maturity.map((m) => m.site))].join(', ')}, from GDD accumulated since planting.
                </p>
              ) : (
                <p className="mt-2">
                  Physiological maturity (black layer) arrives once a hybrid has accumulated enough GDD since planting. The window
                  and its method are published with the final results; no date is shown before then.
                </p>
              )}
            </div>
          </div>
        </Section>

        <Section
          id="uav"
          title="Satellite vs UAV"
          lead={
            <>
              Does adding drone imagery to satellite lower the error enough to pay for a flight? The comparison must be matched:
              the same plots, dates, validation split and model framework, with and without UAV.
              {uavSites.length > 0 &&
                ` UAV imagery in the challenge data exists for ${uavSites.map((s) => s.name).join(', ')} only.`}
            </>
          }
        >
          {uav?.matched ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-left">
                <thead>
                  <tr className="border-b border-line-strong text-[13px] text-muted">
                    <th scope="col" className="py-2.5 pr-4 font-medium">
                      Imagery
                    </th>
                    <th scope="col" className="py-2.5 pr-4 text-right font-medium">
                      MAE (bu/ac)
                    </th>
                    <th scope="col" className="py-2.5 pr-4 text-right font-medium">
                      RMSE (bu/ac)
                    </th>
                    <th scope="col" className="py-2.5 text-right font-medium">
                      R²
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Satellite only', uav.satelliteOnly],
                    ['Satellite + UAV', uav.satellitePlusUav],
                  ].map(([label, v]) => {
                    const variant = v as typeof uav.satelliteOnly;
                    return (
                      <tr key={label as string} className="border-b border-line text-[15px]">
                        <td className="py-3 pr-4 font-medium text-ink">{label as string}</td>
                        <td className="data py-3 pr-4 text-right text-ink">{variant.mae.toFixed(1)}</td>
                        <td className="data py-3 pr-4 text-right text-ink-soft">{variant.rmse?.toFixed(1) ?? '—'}</td>
                        <td className="data py-3 text-right text-ink-soft">{variant.r2?.toFixed(2) ?? '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="mt-3 text-[13px] text-muted">
                {[
                  uav.plots && `${uav.plots} plots`,
                  uav.sites.join(', '),
                  uav.dap != null && `${uav.dap} days after planting`,
                  uav.validation,
                  uav.framework,
                ]
                  .filter(Boolean)
                  .join(' · ')}
                {uav.note ? `. ${uav.note}` : ''}
              </p>
            </div>
          ) : (
            <Pending>
              The matched satellite-only vs satellite + UAV comparison appears here when the final run publishes it.
            </Pending>
          )}
        </Section>

        <Section id="leakage" title="Leakage safeguards">
          <div className="rounded-2xl border border-leaf-200 bg-leaf-50/60 p-6 sm:p-8">
            <p className="text-[20px] font-semibold tracking-[-0.015em] text-ink">
              Every forecast uses only data that would have been available on that date.
            </p>
            <ul className="mt-4 grid gap-3 text-[14px] leading-relaxed text-ink-soft md:grid-cols-2">
              <li>
                One feature pipeline serves training and forecasts; it drops anything dated after the forecast date and fails if
                any remains.
              </li>
              <li>Imagery features at each stage use only the passes acquired by then.</li>
              <li>Models are validated on sites or plots held out of training, never on the plots they learned from.</li>
              <li>The weather outlook never uses the forecast season as one of its historical seasons.</li>
            </ul>
          </div>
        </Section>

        <Section
          id="sources"
          title="Data sources"
          lead="The trial data behind the forecasts, the public data looked up for each plot, and the models."
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-left">
              <thead>
                <tr className="border-b border-line-strong text-[13px] text-muted">
                  <th scope="col" className="py-3 pr-6 font-medium">
                    Source
                  </th>
                  <th scope="col" className="py-3 pr-6 font-medium">
                    Purpose
                  </th>
                  <th scope="col" className="py-3 font-medium">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.id} className="border-b border-line">
                    <td className="py-3.5 pr-6 text-[15px] font-medium text-ink">{s.shortName}</td>
                    <td className="py-3.5 pr-6 text-[15px] text-ink-soft">{s.purpose}</td>
                    <td className="py-3.5">
                      <DataBadge variant={s.role} label={SOURCE_BADGE[s.role]} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {forecast && forecast.fullVegetationSeries.length > 0 && (
              <p className="mt-4 text-[13px] text-muted">
                Satellite passes for {forecast.field.name}:{' '}
                <span className="data">
                  {[...new Set(forecast.fullVegetationSeries.map((o) => o.date))].sort().map(formatDay).join(', ')}
                </span>
                .
              </p>
            )}
          </div>
        </Section>
      </div>

      <Reveal className="mt-24 flex flex-col items-start justify-between gap-6 border-t border-line pt-10 sm:flex-row sm:items-center">
        <p className="text-[18px] font-medium tracking-[-0.01em] text-ink">See it applied to the trial plots.</p>
        <Link
          to="dashboard"
          className="lift group inline-flex items-center gap-2 rounded-full bg-leaf-700 px-5 py-2.5 text-[15px] font-medium text-white hover:bg-leaf-800 hover:shadow-lift"
        >
          View forecast
          <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
        </Link>
      </Reveal>
    </div>
  );
}
