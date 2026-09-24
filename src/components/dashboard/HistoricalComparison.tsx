import { useEffect, useRef, useState } from 'react';
import { motion, useInView, useReducedMotion } from 'motion/react';
import type { HistoricalContext, YieldHistory } from '../../types/agricultural';
import { AnimatedNumber } from '../common/AnimatedNumber';
import { DATA_TRANSITION, EASE_OUT } from '../../utils/motion';
import { formatRetrieved, formatSignedPercent } from '../../utils/formatters';

interface HistoricalComparisonProps {
  /** Demo scenario values, shown when county yields aren't available. */
  historical: HistoricalContext;
  currentForecastYield: number;
  seasonYear: number;
  /** County yields from USDA NASS for the field's county, when connected. */
  countyHistory?: YieldHistory | null;
  /** Why county yields are missing, e.g. no API key yet. */
  countyNote?: string | null;
}

export function HistoricalComparison({ historical, currentForecastYield, seasonYear, countyHistory, countyNote }: HistoricalComparisonProps) {
  const reduce = useReducedMotion();
  const county = countyHistory && countyHistory.fiveYearAverage !== null ? countyHistory : null;
  const average = county ? (county.fiveYearAverage as number) : historical.regional5YearAvg;
  const delta = ((currentForecastYield - average) / average) * 100;
  const rows = county
    ? [
        ...county.years.slice(-5).map((y) => ({ year: y.year, type: 'historical' as const, value: y.yield })),
        { year: seasonYear, type: 'forecast' as const, value: currentForecastYield },
      ]
    : historical.yearlyYields.map((item) => ({
        ...item,
        value: item.type === 'forecast' ? currentForecastYield : item.yield,
      }));
  const max = Math.max(...rows.map((r) => r.value), average) * 1.04;
  const listRef = useRef<HTMLUListElement>(null);
  const inView = useInView(listRef, { once: true, margin: '0px 0px -10% 0px' });
  const shown = inView || !!reduce;
  // After the entrance, bars respond to scrubbing with the shared data transition.
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    if (!shown || entered) return;
    const id = window.setTimeout(() => setEntered(true), 1100);
    return () => window.clearTimeout(id);
  }, [shown, entered]);

  return (
    <section aria-labelledby="history-heading">
      <h2 id="history-heading" className="text-[16px] font-semibold tracking-[-0.01em] text-ink">
        Historical context
      </h2>

      <dl className="mt-5 grid grid-cols-3 gap-4">
        <div>
          <dt className="text-[13px] text-muted">Current forecast</dt>
          <dd className="data-tight mt-1 text-[24px] font-medium text-ink">
            <AnimatedNumber value={currentForecastYield} decimals={0} />
          </dd>
        </div>
        <div>
          <dt className="text-[13px] text-muted">{county ? '5-year county average' : '5-year average'}</dt>
          <dd className="data-tight mt-1 text-[24px] font-medium text-ink">{average.toFixed(0)}</dd>
        </div>
        <div>
          <dt className="text-[13px] text-muted">Difference</dt>
          <dd className={`data-tight mt-1 text-[24px] font-medium ${delta >= 0 ? 'text-leaf-700' : 'text-stress-600'}`}>
            <AnimatedNumber value={delta} decimals={1} format={(v) => formatSignedPercent(v)} />
          </dd>
        </div>
      </dl>

      <div className="relative mt-6">
        <ul ref={listRef} className="space-y-[7px]" aria-label="Yield by season, bushels per acre">
          {rows.map((row, i) => {
            const isForecast = row.type === 'forecast';
            return (
              <li key={row.year} className="grid grid-cols-[4.5rem_1fr_3rem] items-center gap-3">
                <span className={`data text-[12px] ${isForecast ? 'font-medium text-ink' : 'text-muted'}`}>
                  {row.year}
                  {isForecast && <span className="ml-1 font-sans text-[11px] text-leaf-700">fcst</span>}
                </span>
                <div className="relative h-2.5" aria-hidden="true">
                  <motion.div
                    className={`h-full w-full origin-left rounded-r-[4px] ${isForecast ? 'bg-leaf-700' : 'bg-[#CBD1D8]'}`}
                    initial={reduce ? false : { scaleX: 0 }}
                    animate={{ scaleX: shown ? row.value / max : 0 }}
                    transition={
                      reduce ? { duration: 0 } : entered ? DATA_TRANSITION : { duration: 0.7, ease: EASE_OUT, delay: i * 0.06 }
                    }
                  />
                </div>
                <span className="data text-right text-[12px] text-ink-soft tabular-nums">{row.value.toFixed(1)}</span>
              </li>
            );
          })}
        </ul>
        {/* Five-year average reference */}
        <div className="pointer-events-none absolute inset-y-[-6px] right-[3.75rem] left-[5.25rem]" aria-hidden="true">
          <div className="absolute inset-y-0 w-px bg-ink/35" style={{ left: `${(average / max) * 100}%` }}>
            <span className="absolute -top-4 left-1/2 -translate-x-1/2 text-[11px] whitespace-nowrap text-muted">5-yr avg</span>
          </div>
        </div>
      </div>

      <p className="mt-6 flex items-baseline gap-2 text-[12px] leading-relaxed text-muted">
        {county && <span className="mt-[5px] h-1.5 w-1.5 shrink-0 self-start rounded-full bg-rain-500" aria-hidden="true" />}
        <span>
          {seasonYear} value is the current forecast ·{' '}
          {county
            ? `USDA NASS corn yields for ${county.county.name}, ${county.county.stateCode} · retrieved ${formatRetrieved(county.retrievedAt)}`
            : `Demo values · ${countyNote ?? 'County yields from USDA NASS are not connected yet.'}`}
        </span>
      </p>
    </section>
  );
}
