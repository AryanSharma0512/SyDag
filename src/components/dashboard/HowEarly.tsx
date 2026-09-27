import { Hourglass } from 'lucide-react';
import type { FinalResults, SitePerformance } from '../../types/results';
import { imageryGain, sitePerformanceFor, stageForDap, stageRow } from '../../services/results';
import { PerformanceByDap, type ChartRow } from '../results/PerformanceByDap';

interface HowEarlyProps {
  results: FinalResults | null;
  error: string | null;
  /** The site being viewed: its own validation is shown when the results carry it. */
  siteId?: string;
  siteName?: string;
  season?: number | null;
  activeDap: number | null;
  /** The viewed forecast's validation stage (e.g. "TP3"). */
  activeStage?: string | null;
  isPresentationMode?: boolean;
}

const r1 = (v: number) => v.toFixed(1);
const r0 = (v: number) => Math.round(v).toString();

function siteRows(site: SitePerformance): ChartRow[] {
  return site.stages.map((s) => ({
    dap: s.dap,
    stage: s.stage,
    label: `${s.stage} · day ${s.dapMin != null && s.dapMax != null && s.dapMin !== s.dapMax ? `${s.dapMin}–${s.dapMax}` : s.dap}`,
    mae: s.mae,
    rmse: s.rmse,
    r2: s.r2,
    n: s.n,
    coverage: s.coverage,
    medianIntervalWidth: s.medianIntervalWidth,
  }));
}

/**
 * When does the forecast become useful? Read from the final results only. With per-site
 * validation, the chart is the viewed site's own: sites differ, and a pooled line would
 * promise an improvement some sites never saw.
 */
export function HowEarly({
  results,
  error,
  siteId,
  siteName,
  season,
  activeDap,
  activeStage,
  isPresentationMode = false,
}: HowEarlyProps) {
  const ready = results?.status === 'ready' && results.performance.length > 0;
  const site = ready ? sitePerformanceFor(results, siteId, season) : null;
  const level = ready && results.interval?.level ? `${Math.round(results.interval.level * 100)}%` : null;
  const text = isPresentationMode ? 'text-[17px]' : 'text-[14px]';

  return (
    <section aria-labelledby="how-early-heading">
      <h2
        id="how-early-heading"
        className={`font-semibold tracking-[-0.015em] text-ink ${isPresentationMode ? 'text-[24px]' : 'text-[19px]'}`}
      >
        How early can we know?
        {site && siteName && <span className="font-normal text-muted"> · {siteName}</span>}
      </h2>
      <p className={`mt-1 max-w-2xl text-muted ${text}`}>
        {site
          ? `How far forecasts at this site typically missed the harvested yield at each satellite stage, in out-of-fold validation.`
          : 'How far the final-yield forecast typically missed in validation, at each point in the season.'}
      </p>

      {error ? (
        <p className="mt-5 text-[14px] text-muted">The final results did not load ({error}).</p>
      ) : results === null ? (
        <div className="ss-skeleton mt-5 h-[220px] rounded-lg" aria-busy="true" aria-label="Loading validation results" />
      ) : !ready ? (
        <div className="mt-5 flex items-start gap-3 rounded-xl border border-dashed border-line-strong px-5 py-6">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-mist text-muted">
            <Hourglass className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <p className="text-[15px] font-medium text-ink">Waiting for the final model run.</p>
            <p className="mt-1 max-w-lg text-[13px] leading-relaxed text-muted">
              Validation error by days after planting, and the earliest point where the forecast is useful, appear here when the
              frozen results are published. Interim numbers are not shown as the answer.
            </p>
          </div>
        </div>
      ) : site ? (
        <SiteView site={site} activeStage={activeStage} activeDap={activeDap} level={level} large={isPresentationMode} text={text} />
      ) : (
        <PooledView results={results} activeStage={activeStage} activeDap={activeDap} large={isPresentationMode} text={text} />
      )}
    </section>
  );
}

function SiteView({
  site,
  activeStage,
  activeDap,
  level,
  large,
  text,
}: {
  site: SitePerformance;
  activeStage?: string | null;
  activeDap: number | null;
  level: string | null;
  large: boolean;
  text: string;
}) {
  const at = stageRow(site.stages, activeStage, activeDap);
  const pre = site.preseason;
  const gain = imageryGain(pre, at);
  const range = level ? `${level} range` : 'prediction range';
  return (
    <>
      <div className="mt-5">
        <PerformanceByDap
          performance={siteRows(site)}
          activeStage={at?.stage ?? null}
          baseline={pre ? { mae: pre.mae, r2: pre.r2, label: 'Before imagery (field records only)' } : null}
          large={large}
        />
      </div>
      {pre?.mae != null && at?.mae != null && (
        <p className={`mt-4 max-w-3xl text-ink-soft ${text}`}>
          With field records alone, forecasts here typically missed by <span className="data font-medium text-ink">{r1(pre.mae)}</span>{' '}
          bu/ac
          {pre.medianIntervalWidth != null && (
            <>
              , with a {range} about <span className="data font-medium text-ink">{r0(pre.medianIntervalWidth)}</span> bu/ac wide
            </>
          )}
          . At this forecast&rsquo;s satellite stage ({at.stage}, day <span className="data">{at.dap}</span>):{' '}
          <span className="data font-medium text-ink">{r1(at.mae)}</span> bu/ac
          {at.medianIntervalWidth != null && (
            <>
              , range about <span className="data font-medium text-ink">{r0(at.medianIntervalWidth)}</span> bu/ac wide
            </>
          )}
          .
          {gain === 'little' && ' So far, satellite imagery has added little at this site.'}
          {gain === 'modest' && ' A modest gain from satellite imagery at this site.'}
        </p>
      )}
    </>
  );
}

function PooledView({
  results,
  activeStage,
  activeDap,
  large,
  text,
}: {
  results: FinalResults;
  activeStage?: string | null;
  activeDap: number | null;
  large: boolean;
  text: string;
}) {
  const perf = results.performance;
  const useful = results.earliestUsefulDap != null ? stageForDap(perf, results.earliestUsefulDap) : null;
  const active = stageRow(perf, activeStage, activeDap);
  return (
    <>
      <div className="mt-5">
        <PerformanceByDap
          performance={perf}
          earliestUsefulDap={results.earliestUsefulDap}
          activeStage={active?.stage ?? null}
          activeDap={active?.stage ? null : activeDap}
          large={large}
        />
      </div>
      {useful && (
        <p className={`mt-4 max-w-2xl text-ink-soft ${text}`}>
          From about <span className="data font-medium text-ink">{useful.dap}</span> days after planting
          {useful.mae != null && (
            <>
              , forecasts typically miss by about <span className="data font-medium text-ink">{Math.round(useful.mae)}</span> bu/ac
            </>
          )}
          .
          {useful.r2 != null &&
            useful.r2 >= 0.5 &&
            ' By this point in the season, the model captured most of the yield differences observed between plots.'}
        </p>
      )}
    </>
  );
}
