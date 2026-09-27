import { useMemo, useState, type PointerEvent } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import type { SitePerformance, StagePerformance, ValidationMetrics } from '../../types/results';
import { monotonePath, nearestIndex, niceTicks, scaleLinear } from '../../utils/chart';
import { EASE_OUT } from '../../utils/motion';
import { useElementWidth, useIsMobile } from '../../utils/hooks';
import { PALETTE as C } from '../../utils/palette';

/** One stage on the chart: the contract's row, plus a site's range width and coverage when known. */
export type ChartRow = StagePerformance & { coverage?: number | null; medianIntervalWidth?: number | null };

interface PerformanceByDapProps {
  performance: ChartRow[];
  earliestUsefulDap?: number | null;
  /** Days after planting of the forecast being viewed, marked on the chart. */
  activeDap?: number | null;
  /** The stage of the forecast being viewed; preferred over `activeDap` when the rows carry stages. */
  activeStage?: string | null;
  /** The error before any imagery (field records only), drawn as a dashed reference line. */
  baseline?: { mae?: number | null; r2?: number | null; label: string } | null;
  large?: boolean;
}

const fmt = (v: number | null | undefined, digits = 1) => (v == null ? '—' : v.toFixed(digits));
const pct = (v: number) => `${Math.round(v * 100)}%`;

/**
 * Validation error by days after planting: one line (MAE in bu/ac, or R² when the
 * results carry no MAE), never two measures on two axes. R² sits in an aligned row
 * under the axis so each stage's pair can be read together. When the rows name their
 * stages (TP1…), the axis leads with the stage, since its day can differ between sites.
 */
export function PerformanceByDap({
  performance,
  earliestUsefulDap,
  activeDap,
  activeStage,
  baseline,
  large = false,
}: PerformanceByDapProps) {
  const reduce = useReducedMotion();
  const isMobile = useIsMobile();
  const [wrapRef, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const metric: 'mae' | 'r2' = performance.some((p) => p.mae != null) ? 'mae' : 'r2';
  const points = useMemo(() => performance.filter((p) => p[metric] != null), [performance, metric]);
  const showR2Row = metric === 'mae' && performance.some((p) => p.r2 != null);
  const hasStage = points.some((p) => p.stage);
  const base = baseline?.[metric] ?? null;
  const activeIndex = activeStage ? points.findIndex((p) => p.stage === activeStage) : -1;

  const rowGap = large ? 20 : 18;
  const axisRows = [hasStage && 'Stage', 'Day', showR2Row && 'R²'].filter(Boolean) as string[];
  const plotHeight = large ? 280 : isMobile ? 180 : 220;
  const hasMarker = activeIndex >= 0 || activeDap != null;
  const margin = { top: hasMarker ? 42 : 30, right: 20, bottom: 14 + rowGap * axisRows.length, left: 44 };
  const height = margin.top + plotHeight + margin.bottom;

  const geo = useMemo(() => {
    if (width <= 0 || points.length === 0) return null;
    const daps = points.map((p) => p.dap);
    const markerDap = activeIndex >= 0 ? null : activeDap;
    const lo = Math.min(...daps, earliestUsefulDap ?? Infinity, markerDap ?? Infinity);
    const hi = Math.max(...daps, earliestUsefulDap ?? -Infinity, markerDap ?? -Infinity);
    const pad = Math.max(4, (hi - lo) * 0.06);
    const sx = scaleLinear(lo - pad, hi + pad, margin.left, width - margin.right);
    const values = [...points.map((p) => p[metric] as number), ...(base != null ? [base] : [])];
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
      active: activeIndex >= 0 ? pts[activeIndex].x : markerDap != null ? sx(markerDap) : null,
      base: base != null ? sy(base) : null,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, width, plotHeight, metric, earliestUsefulDap, activeDap, activeIndex, base, margin.top, margin.bottom]);

  const usefulIndex = earliestUsefulDap != null ? points.findIndex((p) => p.dap >= earliestUsefulDap) : -1;
  // Direct labels on the first point (unless a baseline already anchors the scale), the useful stage
  // and the viewed stage; never on every point.
  const labelled = new Set([base == null ? 0 : -1, usefulIndex, activeIndex].filter((i) => i >= 0));

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
  const rowY = (row: string) => (geo ? geo.bottom + rowGap * (axisRows.indexOf(row) + 1) : 0);

  return (
    <div>
      <div ref={wrapRef} className="relative" style={{ height }}>
        {geo && (
          <svg
            width={width}
            height={height}
            className="overflow-visible"
            role="img"
            aria-label={`${metric === 'mae' ? 'Typical error (MAE)' : 'R²'} by days after planting: ${
              baseline && base != null ? `${baseline.label}, ${fmt(base, metric === 'mae' ? 1 : 2)}; ` : ''
            }${points
              .map(
                (p) =>
                  `${p.stage ? `${p.stage}, ` : ''}day ${p.dap}, ${fmt(p[metric], metric === 'mae' ? 1 : 2)}${unit ? ` ${unit}` : ''}`,
              )
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
                <line x1={geo.active} x2={geo.active} y1={margin.top - 8} y2={geo.bottom} stroke={C.faint} strokeWidth={1} />
                <text
                  x={geo.active}
                  y={margin.top - 14}
                  textAnchor={geo.active > width - 60 ? 'end' : geo.active < margin.left + 40 ? 'start' : 'middle'}
                  className={`fill-ink-soft font-medium ${tick}`}
                >
                  This forecast
                </text>
              </g>
            )}

            {baseline && geo.base !== null && (
              <g>
                <line
                  x1={margin.left}
                  x2={width - margin.right}
                  y1={geo.base}
                  y2={geo.base}
                  stroke={C.soil500}
                  strokeWidth={1.5}
                  strokeDasharray="5 4"
                />
                <text
                  // Opposite the viewed stage, so the two labels never collide.
                  x={geo.active !== null && geo.active > width / 2 ? margin.left + 4 : width - margin.right}
                  y={geo.base - 6}
                  textAnchor={geo.active !== null && geo.active > width / 2 ? 'start' : 'end'}
                  stroke={C.surface}
                  strokeWidth={4}
                  paintOrder="stroke"
                  className={`fill-ink-soft ${tick}`}
                >
                  {baseline.label} <tspan className="data font-medium">{fmt(base, metric === 'mae' ? 1 : 2)}</tspan>
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
              const emphasis = i === usefulIndex || i === activeIndex;
              return (
                <g key={p.stage ?? p.dap}>
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r={emphasis ? 6.5 : 4.5}
                    fill={emphasis ? C.leaf700 : C.leaf500}
                    stroke={C.surface}
                    strokeWidth={2}
                  />
                  {labelled.has(i) && (
                    <text
                      x={pt.x}
                      y={pt.y - 12}
                      textAnchor="middle"
                      stroke={C.surface}
                      strokeWidth={4}
                      paintOrder="stroke"
                      className={`data fill-ink font-medium ${tick}`}
                    >
                      {fmt(p[metric], metric === 'mae' ? 1 : 2)}
                    </text>
                  )}
                  {hasStage && (
                    <text
                      x={pt.x}
                      y={rowY('Stage')}
                      textAnchor="middle"
                      className={`${i === activeIndex ? 'fill-ink font-semibold' : 'fill-ink-soft font-medium'} ${tick}`}
                    >
                      {p.stage ?? ''}
                    </text>
                  )}
                  <text x={pt.x} y={rowY('Day')} textAnchor="middle" className={`data fill-muted tabular-nums ${tick}`}>
                    {p.dap}
                  </text>
                  {showR2Row && (
                    <text x={pt.x} y={rowY('R²')} textAnchor="middle" className={`data fill-ink-soft tabular-nums ${tick}`}>
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
            {axisRows.map((row) => (
              <text key={row} x={4} y={rowY(row)} className={`fill-muted font-medium ${tick}`}>
                {row}
              </text>
            ))}

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
              className="pointer-events-none absolute top-0 left-0 z-10 w-[220px] rounded-xl border border-line bg-surface/95 px-3.5 py-3 text-[12px] shadow-lift backdrop-blur-sm"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, x: tip.at.x > width - 250 ? tip.at.x - 234 : tip.at.x + 14, y: Math.max(0, tip.at.y - 40) }}
              exit={{ opacity: 0, transition: { duration: 0.1 } }}
              transition={{ duration: 0.15 }}
            >
              <div className="font-medium text-ink">
                {tip.p.label ?? (
                  <>
                    Day <span className="data">{tip.p.dap}</span>
                  </>
                )}
              </div>
              <dl className="mt-2 space-y-1 border-t border-line pt-2">
                {(
                  [
                    ['Typical error (MAE)', tip.p.mae, (v: number) => `${v.toFixed(1)} bu/ac`],
                    ['RMSE', tip.p.rmse, (v: number) => `${v.toFixed(1)} bu/ac`],
                    ['R² (variation explained)', tip.p.r2, (v: number) => v.toFixed(2)],
                    ['Median range width', tip.p.medianIntervalWidth, (v: number) => `${v.toFixed(0)} bu/ac`],
                    ['Yields inside range', tip.p.coverage, pct],
                    ['Plots', tip.p.n, (v: number) => v.toLocaleString('en-US')],
                  ] as Array<[string, number | null | undefined, (v: number) => string]>
                )
                  .filter(([, v]) => v != null)
                  .map(([k, v, show]) => (
                    <div key={k} className="flex justify-between gap-3">
                      <dt className="text-muted">{k}</dt>
                      <dd className="data text-ink-soft">{show(v as number)}</dd>
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
  const hasR2 = performance.some((p) => p.r2 != null);
  const hasStage = performance.some((p) => p.stage);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] text-left">
        <caption className="sr-only">Validation results by days after planting</caption>
        <thead>
          <tr className="border-b border-line-strong text-[13px] text-muted">
            <th scope="col" className="py-3 pr-6 font-medium">
              {hasStage ? 'Stage' : 'Days after planting'}
            </th>
            <th scope="col" className="py-3 pr-6 font-medium">
              {hasStage ? 'Days after planting (median · range across sites)' : 'Stage'}
            </th>
            <th scope="col" className="py-3 pr-6 text-right font-medium">
              MAE (bu/ac)
            </th>
            <th scope="col" className="py-3 pr-6 text-right font-medium">
              RMSE (bu/ac)
            </th>
            {hasR2 && (
              <th scope="col" className="py-3 pr-6 text-right font-medium">
                R²
              </th>
            )}
            <th scope="col" className="py-3 text-right font-medium">
              Plots
            </th>
          </tr>
        </thead>
        <tbody>
          {performance.map((p) => (
            <tr key={p.stage ?? p.dap} className={`border-b border-line ${p.dap === earliestUsefulDap ? 'bg-leaf-50/70' : ''}`}>
              <td className="data py-3 pr-6 text-[15px] text-ink">
                {hasStage ? p.stage : p.dap}
                {p.dap === earliestUsefulDap && <span className="ml-2 font-sans text-[12px] text-leaf-700">earliest useful</span>}
              </td>
              <td className="py-3 pr-6 text-[15px] text-ink-soft">
                {hasStage ? (
                  <>
                    <span className="data">{p.dap}</span>
                    {p.label?.includes('DAP ') && (
                      <span className="data ml-2 text-[13px] text-muted">{p.label.split('DAP ')[1]}</span>
                    )}
                  </>
                ) : (
                  (p.label ?? '—')
                )}
              </td>
              <td className="data py-3 pr-6 text-right text-[15px] text-ink tabular-nums">{fmt(p.mae, 2)}</td>
              <td className="data py-3 pr-6 text-right text-[15px] text-ink-soft tabular-nums">{fmt(p.rmse, 2)}</td>
              {hasR2 && <td className="data py-3 pr-6 text-right text-[15px] text-ink-soft tabular-nums">{fmt(p.r2, 2)}</td>}
              <td className="data py-3 text-right text-[15px] text-ink-soft tabular-nums">{p.n?.toLocaleString('en-US') ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One site's validation, pre-season baseline first, then each satellite stage. */
export function SiteValidationTable({
  site,
  levelLabel = '90%',
  activeStage,
}: {
  site: SitePerformance;
  /** The nominal level of the prediction range, e.g. "90%". */
  levelLabel?: string;
  activeStage?: string | null;
}) {
  const rows: Array<{ key: string; stage: string; day: string; m: ValidationMetrics }> = [
    ...(site.preseason ? [{ key: 'pre', stage: 'Before imagery', day: 'field records only', m: site.preseason }] : []),
    ...site.stages.map((s) => ({
      key: s.stage,
      stage: s.stage,
      day: s.dapMin != null && s.dapMax != null && s.dapMin !== s.dapMax ? `${s.dapMin}–${s.dapMax}` : String(s.dap),
      m: s,
    })),
  ];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] text-left">
        <caption className="sr-only">Validation by satellite stage at {site.site}</caption>
        <thead>
          <tr className="border-b border-line-strong text-[13px] text-muted">
            <th scope="col" className="py-3 pr-5 font-medium">
              Stage
            </th>
            <th scope="col" className="py-3 pr-5 font-medium">
              Days after planting
            </th>
            <th scope="col" className="py-3 pr-5 text-right font-medium">
              MAE (bu/ac)
            </th>
            <th scope="col" className="py-3 pr-5 text-right font-medium">
              RMSE
            </th>
            <th scope="col" className="py-3 pr-5 text-right font-medium">
              R²
            </th>
            <th scope="col" className="py-3 pr-5 text-right font-medium">
              Inside {levelLabel} range
            </th>
            <th scope="col" className="py-3 text-right font-medium">
              Median range width
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ key, stage, day, m }) => (
            <tr
              key={key}
              className={`border-b border-line text-[14px] ${key === 'pre' ? 'text-muted' : ''} ${key === activeStage ? 'bg-leaf-50/70' : ''}`}
            >
              <td className={`py-2.5 pr-5 ${key === 'pre' ? '' : 'data text-ink'}`}>
                {stage}
                {key === activeStage && <span className="ml-2 font-sans text-[12px] text-leaf-700">this forecast</span>}
              </td>
              <td className={`py-2.5 pr-5 ${key === 'pre' ? 'text-[13px]' : 'data text-ink-soft'}`}>{day}</td>
              <td className="data py-2.5 pr-5 text-right text-ink tabular-nums">{fmt(m.mae, 2)}</td>
              <td className="data py-2.5 pr-5 text-right text-ink-soft tabular-nums">{fmt(m.rmse, 2)}</td>
              <td className="data py-2.5 pr-5 text-right text-ink-soft tabular-nums">{fmt(m.r2, 2)}</td>
              <td className="data py-2.5 pr-5 text-right text-ink-soft tabular-nums">{m.coverage != null ? pct(m.coverage) : '—'}</td>
              <td className="data py-2.5 text-right text-ink-soft tabular-nums">
                {m.medianIntervalWidth != null ? `${m.medianIntervalWidth.toFixed(0)} bu/ac` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
