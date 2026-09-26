import { useMemo, useState, type PointerEvent } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ChevronDown } from 'lucide-react';
import type { ModelInfo } from '../../types/agricultural';
import { APP_CONFIG } from '../../config/appConfig';
import { monotonePath, nearestIndex, niceTicks, scaleLinear, toTime } from '../../utils/chart';
import { DATA_TRANSITION, EASE_OUT } from '../../utils/motion';
import { useElementWidth, useIsMobile } from '../../utils/hooks';
import { PALETTE as C } from '../../utils/palette';
import { formatDay } from '../../utils/formatters';
import { imageryLabel } from '../../utils/imagery';
import { DataBadge } from '../common/DataBadge';

interface ModelReliabilityProps {
  models: ModelInfo[] | null;
  error: string | null;
  season: number;
  /** The dashboard's selected forecast date (ISO); its point is highlighted. */
  activeDate: string;
  /** The selected plot's satellite passes, to say what each date had seen. */
  passes: string[];
  datasetLabel: string | null;
}

interface Point {
  date: string;
  model: ModelInfo;
}

/**
 * Validation error of the model behind each forecast date, from GET /api/models.
 * New model exports redraw it; nothing here is specific to the practice models.
 */
export function ModelReliability({ models, error, season, activeDate, passes, datasetLabel }: ModelReliabilityProps) {
  const reduce = useReducedMotion();
  const isMobile = useIsMobile();
  const [wrapRef, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);
  const threshold = APP_CONFIG.acceptableMaeBuAc;

  const points: Point[] = useMemo(
    () =>
      (models ?? [])
        .filter((m): m is ModelInfo & { asOf: string } => m.asOf !== null)
        .map((m) => ({ date: `${season}-${m.asOf}`, model: m }))
        .sort((a, b) => a.date.localeCompare(b.date)),
    [models, season],
  );
  const hasHoldout = points.some((p) => p.model.holdout);
  const holdoutGroup = points.find((p) => p.model.holdout)?.model.holdout?.group.replace(/^site:\s*/i, '');

  const plotHeight = isMobile ? 170 : 210;
  const margin = { top: 20, right: 16, bottom: 50, left: 40 };
  const height = margin.top + plotHeight + margin.bottom;

  const geo = useMemo(() => {
    if (width <= 0 || points.length === 0) return null;
    const times = points.map((p) => toTime(p.date));
    const x0 = margin.left + 18;
    const x1 = width - margin.right - 18;
    const sx = points.length > 1 ? scaleLinear(times[0], times[times.length - 1], x0, x1) : () => (x0 + x1) / 2;
    const values = points.flatMap((p) => [p.model.mae, p.model.holdout?.mae ?? 0, threshold ?? 0]);
    const top = Math.max(1, ...values) * 1.08;
    const ticks = niceTicks(0, top, 4);
    // niceTicks stops at or below the top; extend one step so every value is on the plot.
    if (ticks[ticks.length - 1] < top) ticks.push(ticks[ticks.length - 1] + (ticks[1] - ticks[0]));
    const yMax = ticks[ticks.length - 1];
    const bottom = margin.top + plotHeight;
    const sy = scaleLinear(0, yMax, bottom, margin.top);
    const cv = points.map((p, i) => ({ x: sx(times[i]), y: sy(p.model.mae) }));
    const held = points.map((p, i) => (p.model.holdout ? { x: sx(times[i]), y: sy(p.model.holdout.mae) } : null));
    return {
      bottom,
      sy,
      cv,
      held,
      cvLine: monotonePath(cv),
      heldLine: held.every(Boolean) ? monotonePath(held as Array<{ x: number; y: number }>) : '',
      ticks: ticks.filter((t) => t > 0).map((t) => ({ value: t, y: sy(t) })),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, width, plotHeight, threshold]);

  const activeIndex = points.findIndex((p) => p.date === activeDate);
  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;

  const onPointerMove = (event: PointerEvent<SVGRectElement>) => {
    if (!geo || event.pointerType !== 'mouse') return;
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!rect) return;
    setHover(nearestIndex(geo.cv.map((p) => p.x), event.clientX - rect.left));
  };

  const hovered = hover !== null && geo ? hover : null;
  const tip = hovered !== null ? points[hovered] : null;

  return (
    <section className="flex h-full min-w-0 flex-col" aria-labelledby="reliability-heading">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="reliability-heading" className="text-[16px] font-semibold tracking-[-0.01em] text-ink">
            When does the forecast become useful?
          </h2>
          <p className="mt-1 text-[14px] text-muted">
            Validation error of the model behind each forecast date. Lower error means the model generalized better during
            validation.
          </p>
        </div>
        {datasetLabel && points.length > 0 && (
          <DataBadge variant={/challenge/i.test(datasetLabel) ? 'challenge' : 'practice'} label={datasetLabel} className="shrink-0" />
        )}
      </div>

      {error ? (
        <p className="mt-6 text-[14px] text-muted">Validation results did not load ({error}).</p>
      ) : models === null ? (
        <div className="ss-skeleton mt-6 h-[240px] rounded-lg" aria-busy="true" aria-label="Loading validation results" />
      ) : points.length === 0 ? (
        <p className="mt-6 rounded-xl border border-dashed border-line-strong px-4 py-6 text-[14px] text-muted">
          {APP_CONFIG.demoMode
            ? 'The demo build has no trained models. Validation error appears when the dashboard runs on the SoilSignal API.'
            : 'No dated models are loaded, so there is nothing to compare across the season yet.'}
        </p>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-[2px] w-4 rounded-full bg-leaf-700" aria-hidden="true" />
              Cross-validation, other sites
            </span>
            {hasHoldout && (
              <span className="inline-flex items-center gap-1.5">
                <svg width="16" height="2" aria-hidden="true">
                  <line x1="0" x2="16" y1="1" y2="1" stroke={C.faint} strokeWidth={2} strokeDasharray="4 3" />
                </svg>
                Held-out site{holdoutGroup ? `: ${holdoutGroup}` : ''}
              </span>
            )}
            <span className="data">MAE, bu/ac</span>
          </div>

          <div ref={wrapRef} className="relative mt-2" style={{ height }}>
            {geo && (
              <svg
                width={width}
                height={height}
                className="overflow-visible"
                role="img"
                aria-label={`Validation mean absolute error by forecast date: ${points
                  .map((p) => `${formatDay(p.date)} ${p.model.mae.toFixed(1)}`)
                  .join(', ')} bushels per acre.`}
              >
                {geo.ticks.map((t) => (
                  <g key={t.value}>
                    <line x1={margin.left} x2={width - margin.right} y1={t.y} y2={t.y} stroke={C.line} />
                    <text x={margin.left - 8} y={t.y + 4} textAnchor="end" className="data fill-faint text-[10.5px] tabular-nums">
                      {t.value}
                    </text>
                  </g>
                ))}
                <line x1={margin.left} x2={width - margin.right} y1={geo.bottom} y2={geo.bottom} stroke={C.lineStrong} />

                {threshold !== null && (
                  <g>
                    <line
                      x1={margin.left}
                      x2={width - margin.right}
                      y1={geo.sy(threshold)}
                      y2={geo.sy(threshold)}
                      stroke={C.inkSoft}
                      strokeOpacity={0.6}
                      strokeDasharray="2 4"
                    />
                    <text x={width - margin.right} y={geo.sy(threshold) - 6} textAnchor="end" className="fill-muted text-[11px]">
                      Acceptable MAE ≤ {threshold}
                    </text>
                  </g>
                )}

                {activeIndex >= 0 && (
                  <motion.line
                    y1={margin.top - 6}
                    y2={geo.bottom}
                    stroke={C.leaf700}
                    strokeOpacity={0.32}
                    initial={false}
                    animate={{ x1: geo.cv[activeIndex].x, x2: geo.cv[activeIndex].x }}
                    transition={transition}
                  />
                )}
                {hovered !== null && hovered !== activeIndex && (
                  <line
                    x1={geo.cv[hovered].x}
                    x2={geo.cv[hovered].x}
                    y1={margin.top}
                    y2={geo.bottom}
                    stroke={C.faint}
                    strokeOpacity={0.45}
                  />
                )}

                {geo.heldLine && (
                  <path d={geo.heldLine} fill="none" stroke={C.faint} strokeWidth={2} strokeDasharray="5 4" strokeLinecap="round" />
                )}
                {geo.held.map((p, i) =>
                  p ? <circle key={`h-${i}`} cx={p.x} cy={p.y} r={3.5} fill={C.surface} stroke={C.faint} strokeWidth={2} /> : null,
                )}
                <motion.path
                  d={geo.cvLine}
                  fill="none"
                  stroke={C.leaf700}
                  strokeWidth={2.5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  initial={reduce ? false : { pathLength: 0 }}
                  whileInView={{ pathLength: 1 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.9, ease: EASE_OUT }}
                />
                {geo.cv.map((p, i) => (
                  <circle
                    key={`c-${i}`}
                    cx={p.x}
                    cy={p.y}
                    r={i === activeIndex || i === hovered ? 5 : 4}
                    fill={C.leaf700}
                    stroke={C.surface}
                    strokeWidth={2}
                  />
                ))}

                {/* Direct labels for the selected date only; every value is in the table. */}
                {activeIndex >= 0 && (
                  <g>
                    <text
                      x={geo.cv[activeIndex].x}
                      y={geo.cv[activeIndex].y - 12}
                      textAnchor="middle"
                      className="data fill-ink text-[12px] font-medium"
                      stroke={C.surface}
                      strokeWidth={4}
                      paintOrder="stroke"
                    >
                      {points[activeIndex].model.mae.toFixed(1)}
                    </text>
                    {geo.held[activeIndex] && (
                      <text
                        x={geo.held[activeIndex]!.x}
                        y={geo.held[activeIndex]!.y + (geo.held[activeIndex]!.y > geo.cv[activeIndex].y ? 18 : -12)}
                        textAnchor="middle"
                        className="data fill-muted text-[11px]"
                        stroke={C.surface}
                        strokeWidth={4}
                        paintOrder="stroke"
                      >
                        {points[activeIndex].model.holdout!.mae.toFixed(1)}
                      </text>
                    )}
                  </g>
                )}

                {points.map((p, i) => (
                  <g key={p.date}>
                    <text
                      x={geo.cv[i].x}
                      y={geo.bottom + 18}
                      textAnchor="middle"
                      className={`data text-[11px] ${i === activeIndex ? 'fill-ink font-medium' : 'fill-faint'}`}
                    >
                      {formatDay(p.date)}
                    </text>
                    {passes.length > 0 && !isMobile && (
                      <text x={geo.cv[i].x} y={geo.bottom + 34} textAnchor="middle" className="fill-faint text-[10.5px]">
                        {imageryLabel(passes, p.date).replace('After ', '').replace('Before imagery', 'no imagery')}
                      </text>
                    )}
                  </g>
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
              </svg>
            )}

            <AnimatePresence>
              {geo && tip && hovered !== null && (
                <motion.div
                  className="pointer-events-none absolute top-0 left-0 z-10 w-52 rounded-xl border border-line bg-surface/95 px-3 py-2.5 shadow-lift backdrop-blur-sm"
                  initial={{ opacity: 0, x: geo.cv[hovered].x + (geo.cv[hovered].x > width - 230 ? -222 : 12), y: 8 }}
                  animate={{ opacity: 1, x: geo.cv[hovered].x + (geo.cv[hovered].x > width - 230 ? -222 : 12), y: 8 }}
                  exit={{ opacity: 0, transition: { duration: 0.1 } }}
                  transition={{ type: 'spring', stiffness: 520, damping: 42, mass: 0.6, opacity: { duration: 0.15 } }}
                >
                  <div className="flex items-baseline justify-between gap-2 text-[12px]">
                    <span className="data font-medium text-ink">{formatDay(tip.date)}</span>
                    {passes.length > 0 && <span className="text-muted">{imageryLabel(passes, tip.date)}</span>}
                  </div>
                  <dl className="mt-1.5 space-y-1 border-t border-line pt-1.5 text-[12px]">
                    <TipRow label="Cross-validation MAE" value={tip.model.mae.toFixed(1)} />
                    {tip.model.holdout && <TipRow label="Held-out MAE" value={tip.model.holdout.mae.toFixed(1)} />}
                    <TipRow label="R²" value={tip.model.r2.toFixed(2)} />
                  </dl>
                  <div className="mt-1.5 border-t border-line pt-1.5 text-[11px] text-faint">{tip.model.algorithm}</div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <div className="mt-auto border-t border-line pt-3">
            <button
              type="button"
              onClick={() => setShowTable((v) => !v)}
              aria-expanded={showTable}
              className="inline-flex items-center gap-1 rounded-md py-0.5 text-[13px] font-medium text-ink-soft hover:text-ink"
            >
              Model details
              <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${showTable ? 'rotate-180' : ''}`} />
            </button>
            <AnimatePresence initial={false}>
              {showTable && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3, ease: EASE_OUT }}
                  className="overflow-hidden"
                >
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full min-w-[420px] text-left text-[12px]">
                      <thead className="text-muted">
                        <tr>
                          <th scope="col" className="py-1.5 pr-3 font-medium">Date</th>
                          <th scope="col" className="py-1.5 pr-3 font-medium">Model</th>
                          <th scope="col" className="py-1.5 pr-3 text-right font-medium">CV MAE</th>
                          {hasHoldout && <th scope="col" className="py-1.5 pr-3 text-right font-medium">Held-out MAE</th>}
                          <th scope="col" className="py-1.5 text-right font-medium">R²</th>
                        </tr>
                      </thead>
                      <tbody>
                        {points.map((p) => (
                          <tr key={p.date} className="border-t border-line">
                            <td className="data py-1.5 pr-3 text-ink">{formatDay(p.date)}</td>
                            <td className="py-1.5 pr-3 text-ink-soft">{p.model.algorithm.replace(/Regressor$/, '')}</td>
                            <td className="data py-1.5 pr-3 text-right text-ink tabular-nums">{p.model.mae.toFixed(1)}</td>
                            {hasHoldout && (
                              <td className="data py-1.5 pr-3 text-right text-ink-soft tabular-nums">
                                {p.model.holdout ? p.model.holdout.mae.toFixed(1) : '—'}
                              </td>
                            )}
                            <td className="data py-1.5 text-right text-ink-soft tabular-nums">{p.model.r2.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="mt-2 text-[11px] leading-relaxed text-muted">{points[points.length - 1].model.validation}.</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </>
      )}
    </section>
  );
}

function TipRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="data text-ink-soft">{value}</dd>
    </div>
  );
}
