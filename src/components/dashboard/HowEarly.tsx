import { Hourglass } from 'lucide-react';
import type { FinalResults } from '../../types/results';
import { stageForDap } from '../../services/results';
import { PerformanceByDap } from '../results/PerformanceByDap';

interface HowEarlyProps {
  results: FinalResults | null;
  error: string | null;
  activeDap: number | null;
  isPresentationMode?: boolean;
}

/**
 * When does the forecast become useful? Read from the final results only: the chart
 * waits for the frozen run rather than showing interim numbers as the answer.
 */
export function HowEarly({ results, error, activeDap, isPresentationMode = false }: HowEarlyProps) {
  const ready = results?.status === 'ready' && results.performance.length > 0;
  const perf = ready ? results.performance : [];
  const first = perf.find((p) => p.mae != null);
  const useful = ready && results.earliestUsefulDap != null ? stageForDap(perf, results.earliestUsefulDap) : null;
  const improved = first?.mae != null && useful?.mae != null && useful.mae < first.mae;

  return (
    <section aria-labelledby="how-early-heading">
      <h2
        id="how-early-heading"
        className={`font-semibold tracking-[-0.015em] text-ink ${isPresentationMode ? 'text-[24px]' : 'text-[19px]'}`}
      >
        How early can we know?
      </h2>
      <p className={`mt-1 max-w-2xl text-muted ${isPresentationMode ? 'text-[17px]' : 'text-[14px]'}`}>
        {improved
          ? 'Satellite imagery carries little yield information early in the season. As the crop develops, the model becomes substantially more useful.'
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
      ) : (
        <>
          <div className="mt-5">
            <PerformanceByDap
              performance={perf}
              earliestUsefulDap={results.earliestUsefulDap}
              activeDap={activeDap}
              large={isPresentationMode}
            />
          </div>
          {useful && (
            <p className={`mt-4 max-w-2xl text-ink-soft ${isPresentationMode ? 'text-[17px]' : 'text-[14px]'}`}>
              From about <span className="data font-medium text-ink">{useful.dap}</span> days after planting
              {useful.mae != null && (
                <>
                  , forecasts typically miss by about <span className="data font-medium text-ink">{Math.round(useful.mae)}</span>{' '}
                  bu/ac
                </>
              )}
              .
              {useful.r2 != null &&
                useful.r2 >= 0.5 &&
                ' By this point in the season, the model captured most of the yield differences observed between plots.'}
            </p>
          )}
        </>
      )}
    </section>
  );
}
