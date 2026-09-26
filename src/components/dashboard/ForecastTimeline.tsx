import { useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ChevronDown } from 'lucide-react';
import type { ForecastSnapshot } from '../../types/agricultural';
import { bandPath, monotonePath, nearestIndex, niceTicks, scaleLinear, toTime } from '../../utils/chart';
import { DATA_TRANSITION, EASE_OUT } from '../../utils/motion';
import { useElementWidth, useIsMobile } from '../../utils/hooks';
import { PALETTE as C } from '../../utils/palette';
import { formatYield, ratingLabel } from '../../utils/formatters';
import { formatFullDay, imageryLabel, passDescription } from '../../utils/imagery';

interface ForecastTimelineProps {
  fieldKey: string;
  snapshots: ForecastSnapshot[];
  activeIndex: number;
  onSelectIndex: (index: number) => void;
  isPresentationMode?: boolean;
  /** Satellite acquisition dates (ISO), drawn as a lane under the scrubber. */
  passes?: string[];
  plantingDate?: string;
  platform?: string;
}

/** Only the very first draw of a visit is slow and deliberate; field switches redraw faster. */
let hasDrawnOnce = false;

export function ForecastTimeline({
  fieldKey,
  snapshots,
  activeIndex,
  onSelectIndex,
  isPresentationMode = false,
  passes = [],
  plantingDate,
  platform,
}: ForecastTimelineProps) {
  const reduce = useReducedMotion();
  const isMobile = useIsMobile();
  const [wrapRef, width] = useElementWidth<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const [openPass, setOpenPass] = useState<number | null>(null);
  const drawDuration = hasDrawnOnce ? 0.75 : 1.15;
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');

  const plotHeight = isPresentationMode ? 340 : isMobile ? 210 : 290;
  const margin = { top: 36, right: 12, bottom: 64, left: isMobile ? 36 : 46 };
  const height = margin.top + plotHeight + margin.bottom;
  const index = Math.min(activeIndex, snapshots.length - 1);
  const active = snapshots[index];

  // Passes after the last forecast date cannot change any forecast shown, so they are left off.
  const lastDate = snapshots[snapshots.length - 1]?.date ?? '';
  const lanePasses = useMemo(() => passes.filter((d) => d <= lastDate), [passes, lastDate]);
  const lanePlanting = plantingDate && plantingDate <= lastDate ? plantingDate : undefined;
  // "After each pass" only when every pass is followed by a forecast before the next one.
  const everyPass =
    lanePasses.length > 0 &&
    lanePasses.every((p, i) => snapshots.some((s) => s.date >= p && (i === lanePasses.length - 1 || s.date < lanePasses[i + 1])));
  const title = lanePasses.length === 0 ? 'Forecast through the season' : everyPass ? 'Forecast after each satellite pass' : 'Forecast through the satellite passes';

  const geo = useMemo(() => {
    if (width <= 0 || snapshots.length === 0) return null;
    const times = snapshots.map((s) => toTime(s.date));
    const x0 = margin.left + 12;
    const x1 = width - margin.right - 12;
    // The axis starts at planting (or the first pass) when that comes before the first forecast.
    const start = Math.min(times[0], ...[lanePlanting, ...lanePasses].filter(Boolean).map((d) => toTime(d!)));
    const sx = scaleLinear(start, times[times.length - 1], x0, x1);
    const lo = Math.min(...snapshots.map((s) => s.lowerBound));
    const hi = Math.max(...snapshots.map((s) => s.upperBound));
    const yMin = Math.floor((lo - 6) / 10) * 10;
    const yMax = Math.ceil((hi + 4) / 10) * 10;
    const bottom = margin.top + plotHeight;
    const sy = scaleLinear(yMin, yMax, bottom, margin.top);
    const mid = snapshots.map((s, i) => ({ x: sx(times[i]), y: sy(s.yield) }));
    const upper = snapshots.map((s, i) => ({ x: sx(times[i]), y: sy(s.upperBound) }));
    const lower = snapshots.map((s, i) => ({ x: sx(times[i]), y: sy(s.lowerBound) }));

    // Hide scrubber labels that would collide; the active label is always shown.
    const minGap = isMobile ? 46 : 52;
    const labelVisible = mid.map(() => false);
    let lastShown = -Infinity;
    mid.forEach((p, i) => {
      if (p.x - lastShown >= minGap || i === mid.length - 1) {
        labelVisible[i] = true;
        lastShown = p.x;
      }
    });
    if (mid.length > 1 && mid[mid.length - 1].x - mid[mid.length - 2].x < minGap && labelVisible[mid.length - 2]) {
      labelVisible[mid.length - 2] = false;
    }

    return {
      x0,
      x1,
      bottom,
      mid,
      line: monotonePath(mid),
      band: bandPath(upper, lower),
      bandCollapsed: bandPath(mid, mid),
      ticks: niceTicks(yMin, yMax, isMobile ? 3 : 4)
        .filter((t) => t > yMin && t < yMax)
        .map((t) => ({ value: t, y: sy(t) })),
      stops: snapshots.map((s, i) => ({
        offset: x1 === x0 ? 0 : (mid[i].x - x0) / (x1 - x0),
        opacity: 0.05 + Math.max(0, Math.min(1, (s.confidence - 40) / 60)) * 0.15,
      })),
      labelVisible,
      trackY: bottom + 26,
      passes: lanePasses.map((d) => ({ date: d, x: sx(toTime(d)) })),
      planting: lanePlanting ? sx(toTime(lanePlanting)) : null,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshots, width, plotHeight, isMobile, margin.left, lanePasses, lanePlanting]);

  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;

  const indexAtPointer = (clientX: number) => {
    if (!geo || !svgRef.current) return index;
    const rect = svgRef.current.getBoundingClientRect();
    return nearestIndex(
      geo.mid.map((p) => p.x),
      clientX - rect.left,
    );
  };

  const select = (i: number) => {
    if (i !== index) onSelectIndex(i);
  };

  const onPointerDown = (event: PointerEvent<SVGRectElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    select(indexAtPointer(event.clientX));
  };

  const onPointerMove = (event: PointerEvent<SVGRectElement>) => {
    const i = indexAtPointer(event.clientX);
    if (dragging) select(i);
    else if (event.pointerType === 'mouse') setHover(i);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    let next = index;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') next = Math.max(0, index - 1);
    else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') next = Math.min(snapshots.length - 1, index + 1);
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = snapshots.length - 1;
    else return;
    event.preventDefault();
    event.stopPropagation();
    select(next);
  };

  const hovered = hover !== null && !dragging ? hover : null;
  const tooltipPoint = hovered !== null && geo ? geo.mid[hovered] : null;
  const tooltipLeft = tooltipPoint && tooltipPoint.x > width - 240;

  return (
    <div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-[17px] font-semibold tracking-[-0.015em] text-ink">{title}</h2>
          <p className="mt-1 text-[14px] text-muted">
            Move through the observation dates. Each point uses only data available by that date.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 text-[12px] whitespace-nowrap text-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-[2.5px] w-4 rounded-full bg-leaf-700" aria-hidden="true" />
            Predicted yield, <span className="data">bu/ac</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-4 rounded-[3px] bg-leaf-400/25" aria-hidden="true" />
            90% range
          </span>
          <button
            type="button"
            onClick={() => setShowTable((v) => !v)}
            aria-expanded={showTable}
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium text-ink-soft hover:bg-mist hover:text-ink"
          >
            Data table
            <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${showTable ? 'rotate-180' : ''}`} />
          </button>
        </div>
      </div>

      <div
        ref={wrapRef}
        role="slider"
        tabIndex={0}
        aria-label="Forecast date"
        aria-valuemin={0}
        aria-valuemax={snapshots.length - 1}
        aria-valuenow={index}
        aria-valuetext={`${active.displayDate}, ${imageryLabel(passes, active.date).toLowerCase()}: ${formatYield(active.yield)} bushels per acre, 90% range ${formatYield(active.lowerBound)} to ${formatYield(active.upperBound)}, ${active.confidence}% confidence`}
        onKeyDown={onKeyDown}
        className="relative mt-4 -mx-1 rounded-xl px-1 select-none"
        style={{ height }}
      >
        {geo && (
          <svg ref={svgRef} width={width} height={height} className="overflow-visible" aria-hidden="true">
            <defs>
              <linearGradient id={`band-${uid}`} gradientUnits="userSpaceOnUse" x1={geo.x0} x2={geo.x1} y1={0} y2={0}>
                {geo.stops.map((stop, i) => (
                  <stop key={i} offset={stop.offset} stopColor={C.leaf400} stopOpacity={stop.opacity} />
                ))}
              </linearGradient>
              <clipPath id={`past-${uid}`}>
                <motion.rect x={0} y={0} height={height} initial={false} animate={{ width: geo.mid[index].x }} transition={transition} />
              </clipPath>
              <filter id={`thumb-${uid}`} x="-50%" y="-50%" width="200%" height="200%">
                <feDropShadow dx="0" dy="1.5" stdDeviation="2" floodColor={C.ink} floodOpacity="0.2" />
              </filter>
            </defs>

            {/* Recessive grid and y ticks */}
            <g key={`grid-${fieldKey}`}>
              {geo.ticks.map((tick) => (
                <g key={tick.value}>
                  <line x1={margin.left} x2={width - margin.right} y1={tick.y} y2={tick.y} stroke={C.line} strokeWidth={1} />
                  <text x={margin.left - 10} y={tick.y + 4} textAnchor="end" className="data fill-faint text-[11px] tabular-nums">
                    {tick.value}
                  </text>
                </g>
              ))}
              <line x1={margin.left} x2={width - margin.right} y1={geo.bottom} y2={geo.bottom} stroke={C.lineStrong} strokeWidth={1} />
            </g>

            {/* Uncertainty band: dim for the future, full strength for what has been observed. */}
            <g key={`band-${fieldKey}`}>
              <motion.path
                fill={`url(#band-${uid})`}
                initial={reduce ? false : { d: geo.bandCollapsed, opacity: 0 }}
                animate={{ d: geo.band, opacity: 0.5 }}
                transition={{ delay: 0.12, duration: drawDuration * 0.9, ease: EASE_OUT }}
              />
              <g clipPath={`url(#past-${uid})`}>
                <motion.path
                  fill={`url(#band-${uid})`}
                  initial={reduce ? false : { d: geo.bandCollapsed, opacity: 0 }}
                  animate={{ d: geo.band, opacity: 1 }}
                  transition={{ delay: 0.12, duration: drawDuration * 0.9, ease: EASE_OUT }}
                />
              </g>
            </g>

            {/* Prediction line: the future portion dims, the observed portion is bold. */}
            <g key={`line-${fieldKey}`}>
              <motion.path
                d={geo.line}
                fill="none"
                stroke={C.leaf300}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ pathLength: { duration: drawDuration, ease: EASE_OUT }, opacity: { duration: 0.05 } }}
                onAnimationComplete={() => {
                  hasDrawnOnce = true;
                }}
              />
              <g clipPath={`url(#past-${uid})`}>
                <motion.path
                  d={geo.line}
                  fill="none"
                  stroke={C.leaf700}
                  strokeWidth={2.75}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity: 1 }}
                  transition={{ pathLength: { duration: drawDuration, ease: EASE_OUT }, opacity: { duration: 0.05 } }}
                />
              </g>
              {geo.mid.map((p, i) => {
                const past = i <= index;
                return (
                  <motion.circle
                    key={i}
                    cx={p.x}
                    cy={p.y}
                    stroke={C.surface}
                    strokeWidth={2}
                    initial={reduce ? false : { r: 0 }}
                    animate={{ r: hovered === i ? 5 : 3.4, fill: past ? C.leaf700 : C.leaf300 }}
                    transition={{
                      r: reduce ? { duration: 0 } : { delay: hasDrawnOnce ? 0 : 0.25 + i * 0.07, duration: 0.3, ease: EASE_OUT },
                      fill: transition,
                    }}
                  />
                );
              })}
            </g>

            {/* Hover crosshair */}
            {tooltipPoint && hovered !== index && (
              <line
                x1={tooltipPoint.x}
                x2={tooltipPoint.x}
                y1={margin.top}
                y2={geo.bottom}
                stroke={C.faint}
                strokeOpacity={0.45}
                strokeWidth={1}
              />
            )}

            {/* Selected date marker slides rather than jumps */}
            <motion.g
              initial={reduce ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: reduce ? 0 : drawDuration * 0.7, duration: 0.3 }}
            >
              <motion.g initial={false} animate={{ x: geo.mid[index].x }} transition={transition}>
                <line x1={0} x2={0} y1={margin.top - 6} y2={geo.bottom} stroke={C.leaf700} strokeOpacity={0.32} strokeWidth={1} />
                <rect x={-27} y={margin.top - 30} width={54} height={20} rx={10} fill={C.leaf700} />
                <AnimatePresence initial={false}>
                  <motion.text
                    key={active.id}
                    x={0}
                    y={margin.top - 16}
                    textAnchor="middle"
                    className="data fill-white text-[11px] font-medium"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.2 }}
                  >
                    {active.displayDate}
                  </motion.text>
                </AnimatePresence>
              </motion.g>
              <motion.circle
                r={11}
                fill={C.leaf700}
                opacity={0.12}
                initial={false}
                animate={{ cx: geo.mid[index].x, cy: geo.mid[index].y }}
                transition={transition}
              />
              <motion.circle
                r={6}
                fill={C.leaf700}
                stroke={C.surface}
                strokeWidth={2.5}
                initial={false}
                animate={{ cx: geo.mid[index].x, cy: geo.mid[index].y }}
                transition={transition}
              />
              {!reduce && (
                <motion.circle
                  key={`pulse-${index}`}
                  cx={geo.mid[index].x}
                  cy={geo.mid[index].y}
                  r={6}
                  fill="none"
                  stroke={C.leaf700}
                  strokeWidth={1.5}
                  style={{ originX: 0.5, originY: 0.5 }}
                  initial={{ scale: 1, opacity: 0 }}
                  animate={{ scale: 2.6, opacity: [0, 0.5, 0] }}
                  transition={{ delay: 0.2, duration: 0.7, ease: EASE_OUT }}
                />
              )}
            </motion.g>

            {/* Season scrubber */}
            <g>
              <line x1={geo.x0} x2={geo.x1} y1={geo.trackY} y2={geo.trackY} stroke={C.lineStrong} strokeWidth={1.5} strokeLinecap="round" />
              <motion.line
                x1={geo.x0}
                y1={geo.trackY}
                y2={geo.trackY}
                stroke={C.leaf700}
                strokeWidth={2.5}
                strokeLinecap="round"
                initial={false}
                animate={{ x2: geo.mid[index].x }}
                transition={transition}
              />
              {geo.mid.map((p, i) => (
                <motion.circle
                  key={i}
                  cx={p.x}
                  cy={geo.trackY}
                  r={3.5}
                  initial={false}
                  animate={{ fill: i <= index ? C.leaf700 : C.surface, stroke: i <= index ? C.leaf700 : C.lineStrong }}
                  strokeWidth={1.5}
                  transition={transition}
                />
              ))}
              <motion.circle
                cy={geo.trackY}
                r={8}
                fill={C.leaf700}
                stroke={C.surface}
                strokeWidth={3}
                filter={`url(#thumb-${uid})`}
                initial={false}
                animate={{ cx: geo.mid[index].x, r: dragging ? 9.5 : 8 }}
                transition={transition}
              />
              {snapshots.map((s, i) =>
                geo.labelVisible[i] || i === index ? (
                  <text
                    key={s.id}
                    x={geo.mid[i].x}
                    y={geo.trackY + 26}
                    textAnchor={geo.mid[i].x - geo.x0 < 20 ? 'start' : geo.x1 - geo.mid[i].x < 20 ? 'end' : 'middle'}
                    dx={geo.mid[i].x - geo.x0 < 20 ? -8 : geo.x1 - geo.mid[i].x < 20 ? 8 : 0}
                    className={`data text-[11px] transition-[fill] duration-300 ${i === index ? 'fill-ink font-medium' : 'fill-faint'}`}
                  >
                    {s.displayDate}
                  </text>
                ) : null,
              )}
            </g>

            {/* Interaction surface: drag anywhere across the plot or the rail to scrub. */}
            <rect
              x={margin.left}
              y={margin.top - 30}
              width={Math.max(0, width - margin.left - margin.right)}
              height={height - margin.top + 30}
              fill="transparent"
              style={{ touchAction: 'pan-y', cursor: dragging ? 'grabbing' : 'pointer' }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={() => setDragging(false)}
              onPointerCancel={() => setDragging(false)}
              onLostPointerCapture={() => setDragging(false)}
              onPointerLeave={() => setHover(null)}
            />
          </svg>
        )}

        <AnimatePresence>
          {tooltipPoint && hovered !== null && (
            <motion.div
              className="pointer-events-none absolute top-0 left-0 z-10 w-[220px] rounded-xl border border-line bg-surface/95 px-3.5 py-3 shadow-lift backdrop-blur-sm"
              initial={{ opacity: 0, x: tooltipPoint.x + (tooltipLeft ? -234 : 14), y: tooltipPoint.y - 28 }}
              animate={{ opacity: 1, x: tooltipPoint.x + (tooltipLeft ? -234 : 14), y: Math.max(0, tooltipPoint.y - 28) }}
              exit={{ opacity: 0, transition: { duration: 0.12 } }}
              transition={{ type: 'spring', stiffness: 520, damping: 42, mass: 0.6, opacity: { duration: 0.15 } }}
            >
              <div className="flex items-baseline justify-between gap-2 text-[12px]">
                <span className="data font-medium text-ink">{snapshots[hovered].displayDate}</span>
                <span className="text-muted">{snapshots[hovered].stage}</span>
              </div>
              <div className="mt-1.5 flex items-baseline gap-1.5">
                <span className="data-tight text-[22px] font-medium text-ink">{formatYield(snapshots[hovered].yield)}</span>
                <span className="data text-[12px] text-muted">bu/ac</span>
              </div>
              <div className="mt-2 space-y-1 border-t border-line pt-2 text-[12px]">
                <div className="flex justify-between gap-3">
                  <span className="text-muted">90% range</span>
                  <span className="data text-ink-soft">
                    {formatYield(snapshots[hovered].lowerBound)}–{formatYield(snapshots[hovered].upperBound)}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-muted">Confidence</span>
                  <span className="data text-ink-soft">
                    {snapshots[hovered].confidence}% · {ratingLabel(snapshots[hovered].confidenceRating)}
                  </span>
                </div>
                {passes.length > 0 && (
                  <div className="flex justify-between gap-3">
                    <span className="text-muted">Imagery</span>
                    <span className="text-ink-soft">{imageryLabel(passes, snapshots[hovered].date)}</span>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {geo && (geo.passes.length > 0 || geo.planting !== null) && (
        <div className="relative" style={{ height: 58 }}>
          <svg width={width} height={58} className="overflow-visible" aria-hidden="true">
            <text x={margin.left} y={12} className="fill-muted text-[11px] font-medium">
              Satellite observations
            </text>
            <line x1={geo.x0} x2={geo.x1} y1={30} y2={30} stroke={C.line} strokeWidth={1} />
            {geo.planting !== null && (
              <g>
                <line x1={geo.planting} x2={geo.planting} y1={24} y2={36} stroke={C.soil500} strokeWidth={1.5} strokeLinecap="round" />
                <text x={geo.planting} y={52} textAnchor="middle" className="fill-faint text-[10.5px]">
                  Planted
                </text>
              </g>
            )}
            {geo.passes.map((p, i) => {
              const seen = p.date <= active.date;
              return (
                <g key={p.date}>
                  <circle
                    cx={p.x}
                    cy={30}
                    r={openPass === i ? 5 : 4}
                    fill={seen ? C.leaf700 : C.surface}
                    stroke={seen ? C.surface : C.leaf300}
                    strokeWidth={seen ? 2 : 1.5}
                    className="transition-[fill,stroke] duration-300"
                  />
                  <text x={p.x} y={52} textAnchor="middle" className={`data text-[10.5px] ${seen ? 'fill-ink-soft' : 'fill-faint'}`}>
                    {i + 1}
                  </text>
                </g>
              );
            })}
          </svg>
          {geo.passes.map((p, i) => {
            const flip = p.x > width - 190;
            return (
              <div key={p.date} className="absolute" style={{ left: p.x, top: 20 }}>
                <button
                  type="button"
                  aria-label={`Satellite pass ${i + 1}, ${formatFullDay(p.date)}. ${passDescription(platform)}.`}
                  onMouseEnter={() => setOpenPass(i)}
                  onMouseLeave={() => setOpenPass((cur) => (cur === i ? null : cur))}
                  onFocus={() => setOpenPass(i)}
                  onBlur={() => setOpenPass((cur) => (cur === i ? null : cur))}
                  onClick={() => setOpenPass((cur) => (cur === i ? null : i))}
                  className="-ml-[10px] block h-5 w-5 rounded-full"
                />
                <AnimatePresence>
                  {openPass === i && (
                    <motion.div
                      role="tooltip"
                      className={`pointer-events-none absolute bottom-full z-20 mb-2 w-48 rounded-xl border border-line bg-surface p-3 shadow-lift ${
                        flip ? 'right-0 -mr-[10px]' : '-ml-[10px] left-0'
                      }`}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 4, transition: { duration: 0.1 } }}
                      transition={{ duration: 0.16, ease: EASE_OUT }}
                    >
                      <div className="text-[12px] text-muted">Satellite pass {i + 1}</div>
                      <div className="data mt-0.5 text-[13px] font-medium text-ink">{formatFullDay(p.date)}</div>
                      <div className="mt-1 text-[12px] text-muted">{passDescription(platform)}</div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      )}

      <AnimatePresence initial={false}>
        {showTable && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: EASE_OUT }}
            className="overflow-hidden"
          >
            <div className="mt-2 overflow-x-auto rounded-xl border border-line">
              <table className="w-full min-w-[520px] text-left text-[13px]">
                <caption className="sr-only">Forecast snapshots through the growing season</caption>
                <thead className="bg-mist/60 text-[12px] text-muted">
                  <tr>
                    <th scope="col" className="px-4 py-2 font-medium">Date</th>
                    <th scope="col" className="px-4 py-2 font-medium">Stage</th>
                    {passes.length > 0 && <th scope="col" className="px-4 py-2 font-medium">Imagery</th>}
                    <th scope="col" className="px-4 py-2 text-right font-medium">Forecast (bu/ac)</th>
                    <th scope="col" className="px-4 py-2 text-right font-medium">90% range</th>
                    <th scope="col" className="px-4 py-2 text-right font-medium">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshots.map((s, i) => (
                    <tr key={s.id} className={`border-t border-line ${i === index ? 'bg-leaf-50/70' : ''}`}>
                      <td className="data px-4 py-2 text-ink">{s.displayDate}</td>
                      <td className="px-4 py-2 text-ink-soft">{s.stage}</td>
                      {passes.length > 0 && <td className="px-4 py-2 text-ink-soft">{imageryLabel(passes, s.date)}</td>}
                      <td className="data px-4 py-2 text-right text-ink tabular-nums">{formatYield(s.yield)}</td>
                      <td className="data px-4 py-2 text-right text-ink-soft tabular-nums">
                        {formatYield(s.lowerBound)}–{formatYield(s.upperBound)}
                      </td>
                      <td className="data px-4 py-2 text-right text-ink-soft tabular-nums">{s.confidence}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
