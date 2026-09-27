import { motion, useReducedMotion } from 'motion/react';
import type { ForecastPoint, TypicalError } from '../../services/plotForecasts';
import { AnimatedNumber } from '../common/AnimatedNumber';
import { DATA_TRANSITION } from '../../utils/motion';
import { formatFullDay } from '../../utils/imagery';

interface ForecastSummaryProps {
  point: ForecastPoint;
  /** The forecast date before this one, for the change since then. */
  previous?: ForecastPoint;
  /** Range of bounds across the season; the range glyph is drawn against it. */
  seasonDomain: [number, number];
  /** Validation error for this point in the season; null while it is not published. */
  typicalError: TypicalError | null;
  isPresentationMode?: boolean;
}

/**
 * The first thing the dashboard answers: final yield, its prediction range, and how
 * far into the season the forecast is. There is deliberately no "confidence %": the
 * old heuristic was not a probability. Error is shown as validation MAE in bu/ac.
 */
export function ForecastSummary({
  point,
  previous,
  seasonDomain,
  typicalError,
  isPresentationMode = false,
}: ForecastSummaryProps) {
  const reduce = useReducedMotion();
  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;
  const hero = isPresentationMode ? 'text-[88px] sm:text-[112px]' : 'text-[64px] sm:text-[84px]';
  const value = isPresentationMode ? 'text-[26px] sm:text-[30px]' : 'text-[21px] sm:text-[24px]';
  const label = isPresentationMode ? 'text-[15px]' : 'text-[13px]';

  const hasRange = point.lowerBound !== null && point.upperBound !== null;
  const [d0, d1] = seasonDomain;
  const span = Math.max(1, d1 - d0);
  const rangeStart = hasRange ? (point.lowerBound! - d0) / span : 0;
  const rangeWidth = hasRange ? (point.upperBound! - point.lowerBound!) / span : 0;
  const pointAt = (point.yield - d0) / span;
  const change = previous ? Math.round(point.yield - previous.yield) : null;

  return (
    <section
      aria-label="Final yield forecast"
      className="grid gap-8 rounded-2xl border border-line bg-surface p-6 sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:gap-12"
    >
      <div>
        <p className={`font-medium tracking-[0.08em] text-leaf-700 uppercase ${label}`}>Final yield forecast</p>
        <div className="mt-3 flex items-baseline gap-3">
          <span className={`leading-none font-semibold tracking-[-0.045em] text-ink ${hero}`}>
            <AnimatedNumber value={point.yield} decimals={0} from={0} />
          </span>
          <span className={`font-medium text-muted ${isPresentationMode ? 'text-[26px]' : 'text-[20px]'}`}>bu/ac</span>
        </div>
        {previous && change !== null ? (
          <p className={`mt-4 text-muted ${label}`} aria-live="polite">
            <span
              className={`data font-medium ${change <= -5 ? 'text-stress-600' : change >= 5 ? 'text-leaf-700' : 'text-ink-soft'}`}
            >
              {change > 0 ? '+' : change < 0 ? '−' : '±'}
              {Math.abs(change)} bu/ac
            </span>{' '}
            since the {previous.displayDate} forecast
          </p>
        ) : (
          <p className={`mt-4 text-muted ${label}`}>First forecast of the season.</p>
        )}
      </div>

      <dl className="grid content-center gap-5 border-t border-line pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-12">
        <div>
          <dt className={`text-muted ${label}`}>Prediction range</dt>
          <dd className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-2">
            {hasRange ? (
              <>
                <span className={`data font-medium whitespace-nowrap text-ink ${value}`}>
                  <AnimatedNumber value={point.lowerBound!} decimals={0} from={0} />
                  <span className="text-faint"> – </span>
                  <AnimatedNumber value={point.upperBound!} decimals={0} from={0} />
                  <span className="ml-1.5 text-[0.6em] font-normal text-muted">bu/ac</span>
                </span>
                <span className="relative hidden h-1.5 w-28 overflow-x-clip rounded-full bg-mist sm:block" aria-hidden="true">
                  <motion.span
                    className="absolute inset-y-0 left-0 block w-full origin-left rounded-full bg-leaf-200"
                    initial={false}
                    animate={{ x: `${rangeStart * 100}%`, scaleX: rangeWidth }}
                    transition={transition}
                  />
                  <motion.span
                    className="absolute inset-0 block"
                    initial={false}
                    animate={{ x: `${pointAt * 100}%` }}
                    transition={transition}
                  >
                    <span className="absolute -top-[3px] left-0 -ml-px h-3 w-[2px] rounded-full bg-leaf-700" />
                  </motion.span>
                </span>
              </>
            ) : (
              <span className={`text-muted ${label}`}>Not published for this forecast.</span>
            )}
          </dd>
        </div>

        <div>
          <dt className={`text-muted ${label}`}>As of</dt>
          <dd className={`mt-1 font-medium text-ink ${value}`}>
            {point.dap !== null ? (
              <>
                <span className="data">{point.dap}</span> days after planting
              </>
            ) : (
              <span className="data">{point.displayDate}</span>
            )}
          </dd>
          <dd className={`mt-0.5 text-muted ${label}`}>
            {formatFullDay(point.date)}
            {point.stage ? ` · ${point.stage} stage` : ''}
          </dd>
        </div>

        <div>
          <dt className={`text-muted ${label}`}>Typical validation error</dt>
          {typicalError ? (
            <>
              <dd className={`data mt-1 font-medium text-ink ${value}`}>
                ±{Math.round(typicalError.mae)}
                <span className="ml-1.5 text-[0.6em] font-normal text-muted">bu/ac</span>
              </dd>
              <dd className={`mt-0.5 text-muted ${label}`}>Average miss {typicalError.basis}</dd>
            </>
          ) : (
            <dd className={`mt-1 text-muted ${label}`}>Published with the final model results.</dd>
          )}
        </div>
      </dl>
    </section>
  );
}
