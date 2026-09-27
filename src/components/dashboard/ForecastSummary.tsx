import { motion, useReducedMotion } from 'motion/react';
import type { ForecastSnapshot } from '../../types/agricultural';
import { AnimatedNumber } from '../common/AnimatedNumber';
import { DATA_TRANSITION } from '../../utils/motion';

interface ForecastSummaryProps {
  snapshot: ForecastSnapshot;
  /** The forecast date before this one, for the change since then. */
  previous?: ForecastSnapshot;
  /** Range of bounds across the season; the range glyph is drawn against it. */
  seasonDomain: [number, number];
  isPresentationMode?: boolean;
}

/**
 * Farmer-facing summary: final yield first, uncertainty second, date/stage third.
 * We deliberately do not show the old custom "confidence %" heuristic here.
 */
export function ForecastSummary({ snapshot, previous, seasonDomain, isPresentationMode = false }: ForecastSummaryProps) {
  const reduce = useReducedMotion();
  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;
  const valueSize = isPresentationMode ? 'text-[46px] sm:text-[60px]' : 'text-[40px] sm:text-[50px]';
  const secondarySize = isPresentationMode ? 'text-[30px] sm:text-[48px]' : 'text-[26px] sm:text-[42px]';

  const [d0, d1] = seasonDomain;
  const span = Math.max(1, d1 - d0);
  const rangeStart = (snapshot.lowerBound - d0) / span;
  const rangeWidth = (snapshot.upperBound - snapshot.lowerBound) / span;
  const pointAt = (snapshot.yield - d0) / span;
  const change = previous ? Math.round((snapshot.yield - previous.yield) * 10) / 10 : null;

  return (
    <section aria-label="Forecast summary" className="grid grid-cols-2 gap-y-6 sm:grid-cols-3">
      <div className="col-span-2 border-b border-line pb-6 sm:col-span-1 sm:border-r sm:border-b-0 sm:pr-8 sm:pb-0">
        <div className={`data-tight leading-none font-medium text-ink ${valueSize}`}>
          <AnimatedNumber value={snapshot.yield} decimals={1} from={0} />
        </div>
        <div className="data mt-2 text-[13px] text-muted">bu/ac</div>
        <div className="mt-3 text-[14px] text-ink-soft">Final yield forecast</div>
      </div>

      <div className="border-r border-line pr-4 sm:px-8">
        <div className={`data-tight leading-none font-medium whitespace-nowrap text-ink ${secondarySize}`}>
          <AnimatedNumber value={snapshot.lowerBound} decimals={0} from={0} />
          <span className="text-faint">–</span>
          <AnimatedNumber value={snapshot.upperBound} decimals={0} from={0} />
        </div>
        <div className="data mt-2 text-[13px] text-muted">bu/ac</div>
        <div className="mt-3 flex items-center gap-3">
          <span className="text-[14px] text-ink-soft">Prediction range</span>
          <div className="relative hidden h-1.5 w-24 overflow-x-clip rounded-full bg-mist sm:block" aria-hidden="true">
            <motion.div
              className="absolute inset-y-0 left-0 w-full origin-left rounded-full bg-leaf-200"
              initial={false}
              animate={{ x: `${rangeStart * 100}%`, scaleX: rangeWidth }}
              transition={transition}
            />
            <motion.div className="absolute inset-0" initial={false} animate={{ x: `${pointAt * 100}%` }} transition={transition}>
              <span className="absolute -top-[3px] left-0 -ml-px h-3 w-[2px] rounded-full bg-leaf-700" />
            </motion.div>
          </div>
        </div>
      </div>

      <div className="pl-4 sm:pl-8">
        <div className={`data-tight leading-none font-medium text-ink ${secondarySize}`}>{snapshot.displayDate}</div>
        <div className="data mt-2 text-[13px] text-muted">forecast date</div>
        <div className="mt-3 text-[14px] text-ink-soft">{snapshot.stage} stage</div>
      </div>

      <dl className="col-span-2 flex flex-wrap items-baseline gap-x-8 gap-y-1 border-t border-line pt-4 text-[14px] sm:col-span-3" aria-live="polite">
        {previous && change !== null ? (
          <>
            <div className="flex items-baseline gap-2">
              <dt className="text-muted">
                Previous forecast, <span className="data">{previous.displayDate}</span>
              </dt>
              <dd className="data text-ink-soft tabular-nums">{previous.yield.toFixed(1)}</dd>
            </div>
            <div className="flex items-baseline gap-2">
              <dt className="text-muted">Change</dt>
              <dd className={`data font-medium tabular-nums ${change <= -5 ? 'text-stress-600' : change >= 5 ? 'text-leaf-700' : 'text-ink'}`}>
                {change > 0 ? '+' : change < 0 ? '−' : '±'}
                {Math.abs(change).toFixed(1)} <span className="font-normal text-muted">bu/ac</span>
              </dd>
            </div>
          </>
        ) : (
          <div>
            <dt className="text-muted">First forecast of the season; no earlier forecast to compare with.</dt>
          </div>
        )}
      </dl>
    </section>
  );
}
