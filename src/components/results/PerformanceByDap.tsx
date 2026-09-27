import { useMemo, useState, type PointerEvent } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import type { StagePerformance } from '../../types/results';
import { monotonePath, nearestIndex, niceTicks, scaleLinear } from '../../utils/chart';
import { EASE_OUT } from '../../utils/motion';
import { useElementWidth, useIsMobile } from '../../utils/hooks';
import { PALETTE as C } from '../../utils/palette';

interface PerformanceByDapProps {
  performance: StagePerformance[];
  earliestUsefulDap?: number | null;
  /** Days after planting of the forecast being viewed, marked on the chart. */
  activeDap?: number | null;
  large?: boolean;
}

const fmt = (v: number | null | undefined, digits = 1) => (v == null ? '—' : v.toFixed(digits));

/**
 * Validation error by days after planting: one line (MAE in bu/ac, or R² when the
 * results carry no MAE), never two measures on two axes. R² sits in an aligned row
 * under the axis so each stage's pair can be read together.
 */
export function PerformanceByDap({ performance, earliestUsefulDap, activeDap, large = false }: PerformanceByDapProps) {
  const reduce = useReducedMotion();
  const isMobile = useIsMobile();
  const [wrapRef, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const metric: 'mae' | 'r2' = performance.some((p) => p.mae != null) ? 'mae' : 'r2';
  const points = useMemo(() => performance.filter((p) => p[metric] != null), [performance, metric]);
  const showR2Row = metric === 'mae' && performance.some((p) => p.r2 != null);

  const plotHeight = large ? 280 : isMobile ? 180 : 220;
  const margin = { top: 30, right: 20, bottom: 40, left: 44 };
  const r2Row = showR2Row ? 30 : 0;
  const height = margin.top + plotHeight + margin.bottom + r2Row;

  const geo = useMemo(() => {
    if (width <= 0 || points.length === 0) return null;
    const daps = points.map((p) => p.dap);
    const lo = Math.min(...daps, earliestUsefulDap ?? Infinity, activeDap ?? Infinity);
    const hi = Math.max(...daps, earliestUsefulDap ?? -Infinity, activeDap ?? -Infinity);
    const pad = Math.max(4, (hi - lo) * 0.06);
    const sx = scaleLinear(lo - pad, hi + pad, margin.left, width - margin.right);
    const values = points.map((p) => p[metric] as number);
    let y0: number;
    let y1: number;
    if (metric === 'mae') {
      y0 = 0;
      const ticks = niceTicks(0, Math.max(...values) * 1.1, 4);
      y1 =
        ticks[ticks.length - 1] < Math.max(...values) ? ticks[ticks.length - 1] + (ticks[1] - ticks[0]) : ticks[ticks.length - 1];
    } else {
      y0 = Math.min(0, Math.floor(Math.min(...values) * 4) / 4);
      y1 = 1;
    }
    const bottom = margin.top + plotHeight;
    const sy = scaleLinear(y0, y1, bottom, margin.top);
    const pts = points.map((p) => ({ x: sx(p.dap), y: sy(p[metric] as number) }));
    return {
      sx,
      bottom,
      pts,
      line: monotonePath(pts),
      ticks: niceTicks(y0, y1, 4).map((t) => ({ value: t, y: sy(t) })),
      useful: earliestUsefulDap != null ? sx(earliestUsefulDap) : null,
      active: activeDap != null ? sx(activeDap) : null,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, width, plotHeight, metric, earliestUsefulDap, activeDap]);

  const usefulIndex = earliestUsefulDap != null ? points.findIndex((p) => p.dap >= earliestUsefulDap) : -1;
  const labelled = new Set([0, usefulIndex].filter((i) => i >= 0));

  const onPointerMove = (event: PointerEvent<SVGRectElement>) => {
    if (!geo) return;
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!rect) return;
    setHover(
      nearestIndex(
        geo.pts.map((p) => p.x),
        event.clientX - rect.left,
      ),
    );
  };

  const tip = hover !== null && geo ? { p: points[hover], at: geo.pts[hover] } : null;
  const unit = metric === 'mae' ? 'bu/ac' : '';
  const tick = large ? 'text-[13px]' : 'text-[11px]';

  return (
    <div>
      <div ref={wrapRef} className="relative" style={{ height }}>
        {geo && (
          <svg
            width={width}
            height={height}
            className="overflow-visible"
            role="img"
            aria-label={`${metric === 'mae' ? 'Typical error (MAE)' : 'R²'} by days after planting: ${points
              .map((p) => `day ${p.dap}, ${fmt(p[metric], metric === 'mae' ? 1 : 2)}${unit ? ` ${unit}` : ''}`)
              .join('; ')}`}
          >
            {geo.useful !== null && (
              <g>
                <rect
                  x={geo.useful}
                  y={margin.top}
                  width={Math.max(0, width - margin.right - geo.useful)}
                  height={plotHeight}
                  fill={C.leaf50}
                />
                <line x1={geo.useful} x2={geo.useful} y1={margin.top - 6} y2={geo.bottom} stroke={C.leaf400} strokeWidth={1.5} />
                <text x={geo.useful + 6} y={margin.top - 10} className={`fill-leaf-800 font-medium ${tick}`}>
                  Useful from day {earliestUsefulDap}
                </text>
              </g>
            )}

            {geo.ticks.map((t) => (
              <g key={t.value}>
                <line x1={margin.left} x2={width - margin.right} y1={t.y} y2={t.y} stroke={C.line} strokeWidth={1} />
                <text x={margin.left - 8} y={t.y + 4} textAnchor="end" className={`data fill-faint tabular-nums ${tick}`}>
                  {metric === 'mae' ? t.value : t.value.toFixed(2)}
                </text>
              </g>
            ))}
            <text x={margin.left} y={12} className={`fill-muted ${tick}`}>
              {metric === 'mae' ? 'Typical error (MAE), bu/ac · lower is better' : 'R² · higher is better'}
            </text>

            {geo.active !== null && (
              <g>
                <line x1={geo.active} x2={geo.active} y1={margin.top} y2={geo.bottom} stroke={C.faint} strokeWidth={1} />
                <text x={geo.active} y={geo.bottom + 34} textAnchor="middle" className={`fill-ink-soft font-medium ${tick}`}>
                  This forecast
                </text>
              </g>
            )}

            <motion.path
              d={geo.line}
              fill="none"
              stroke={C.leaf700}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              initial={reduce ? false : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.8, ease: EASE_OUT }}
            />

            {geo.pts.map((pt, i) => {
              const p = points[i];
              const emphasis = i === usefulIndex;
              return (
                <g key={p.dap}>
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r={emphasis ? 6.5 : 4.5}
                    fill={emphasis ? C.leaf700 : C.leaf500}
                    stroke={C.surface}
                    strokeWidth={2}
                  />
                  {labelled.has(i) && (
                    <text x={pt.x} y={pt.y - 12} textAnchor="middle" className={`data fill-ink font-medium ${tick}`}>
                      {fmt(p[metric], metric === 'mae' ? 1 : 2)}
                    </text>
                  )}
                  <text x={pt.x} y={geo.bottom + 18} textAnchor="middle" className={`data fill-muted tabular-nums ${tick}`}>
                    {p.dap}
                  </text>
                  {showR2Row && (
                    <text
                      x={pt.x}
                      y={geo.bottom + 40 + r2Row - 12}
                      textAnchor="middle"
                      className={`data fill-ink-soft tabular-nums ${tick}`}
                    >
                      {fmt(p.r2, 2)}
                    </text>
                  )}
                </g>
              );
            })}
            <line
              x1={margin.left}
              x2={width - margin.right}
              y1={geo.bottom}
              y2={geo.bottom}
              stroke={C.lineStrong}
              strokeWidth={1}
            />
            {showR2Row && (
              <text x={4} y={geo.bottom + 40 + r2Row - 12} className={`fill-muted font-medium ${tick}`}>
                R²
              </text>
            )}
            <text x={4} y={geo.bottom + 18} className={`fill-muted font-medium ${tick}`}>
              Day
            </text>

            <rect
              x={margin.left}
              y={margin.top}
              width={Math.max(0, width - margin.left - margin.right)}
              height={plotHeight}
              fill="transparent"
              onPointerMove={onPointerMove}
              onPointerLeave={() => setHover(null)}
            />
            {tip && (
              <circle cx={tip.at.x} cy={tip.at.y} r={8} fill="none" stroke={C.leaf700} strokeWidth={1.5} pointerEvents="none" />
            )}
          </svg>
        )}

        <AnimatePresence>
          {tip && (
            <motion.div
              role="tooltip"
              className="pointer-events-none absolute top-0 left-0 z-10 w-[200px] rounded-xl border border-line bg-surface/95 px-3.5 py-3 text-[12px] shadow-lift backdrop-blur-sm"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, x: tip.at.x > width - 230 ? tip.at.x - 214 : tip.at.x + 14, y: Math.max(0, tip.at.y - 40) }}
              exit={{ opacity: 0, transition: { duration: 0.1 } }}
              transition={{ duration: 0.15 }}
            >
              <div className="font-medium text-ink">
                Day <span className="data">{tip.p.dap}</span>
                {tip.p.label ? <span className="text-muted"> · {tip.p.label}</span> : null}
              </div>
              <dl className="mt-2 space-y-1 border-t border-line pt-2">
                {[
                  ['Typical error (MAE)', tip.p.mae, 1, ' bu/ac'],
                  ['RMSE', tip.p.rmse, 1, ' bu/ac'],
                  ['R²', tip.p.r2, 2, ''],
                  ['Plots', tip.p.n, 0, ''],
                ]
                  .filter(([, v]) => v != null)
                  .map(([k, v, d, u]) => (
                    <div key={k as string} className="flex justify-between gap-3">
                      <dt className="text-muted">{k as string}</dt>
                      <dd className="data text-ink-soft">
                        {(v as number).toFixed(d as number)}
                        {u as string}
                      </dd>
                    </div>
                  ))}
              </dl>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

/** The table view of the same numbers, for Methodology and screen readers. */
export function PerformanceTable({
  performance,
  earliestUsefulDap,
}: {
  performance: StagePerformance[];
  earliestUsefulDap?: number | null;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] text-left">
        <caption className="sr-only">Validation results by days after planting</caption>
        <thead>
          <tr className="border-b border-line-strong text-[13px] text-muted">
            <th scope="col" className="py-3 pr-6 font-medium">
              Days after planting
            </th>
            <th scope="col" className="py-3 pr-6 font-medium">
              Stage
            </th>
            <th scope="col" className="py-3 pr-6 text-right font-medium">
              MAE (bu/ac)
            </th>
            <th scope="col" className="py-3 pr-6 text-right font-medium">
              RMSE (bu/ac)
            </th>
            <th scope="col" className="py-3 pr-6 text-right font-medium">
              R²
            </th>
            <th scope="col" className="py-3 text-right font-medium">
              Plots
            </th>
          </tr>
        </thead>
        <tbody>
          {performance.map((p) => (
            <tr key={p.dap} className={`border-b border-line ${p.dap === earliestUsefulDap ? 'bg-leaf-50/70' : ''}`}>
              <td className="data py-3 pr-6 text-[15px] text-ink">
                {p.dap}
                {p.dap === earliestUsefulDap && <span className="ml-2 font-sans text-[12px] text-leaf-700">earliest useful</span>}
              </td>
              <td className="py-3 pr-6 text-[15px] text-ink-soft">{p.label ?? '—'}</td>
              <td className="data py-3 pr-6 text-right text-[15px] text-ink tabular-nums">{fmt(p.mae)}</td>
              <td className="data py-3 pr-6 text-right text-[15px] text-ink-soft tabular-nums">{fmt(p.rmse)}</td>
              <td className="data py-3 pr-6 text-right text-[15px] text-ink-soft tabular-nums">{fmt(p.r2, 2)}</td>
              <td className="data py-3 text-right text-[15px] text-ink-soft tabular-nums">{p.n ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
