import { useId, useMemo, useRef, useState, type PointerEvent } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { CloudRain, Sprout, Sun, Thermometer, Tractor, type LucideIcon } from 'lucide-react';
import type { EventMarker, VegetationObservation } from '../../types/agricultural';
import { monotonePath, nearestIndex, scaleLinear, toTime } from '../../utils/chart';
import { DATA_TRANSITION, EASE_OUT } from '../../utils/motion';
import { useElementWidth, useIsMobile } from '../../utils/hooks';
import { PALETTE as C } from '../../utils/palette';
import { SegmentedControl } from '../common/SegmentedControl';
import { APP_CONFIG } from '../../config/appConfig';

type Signal = 'ndvi' | 'ndre';

interface CropDevelopmentProps {
  fieldKey: string;
  timeline: VegetationObservation[];
  events: EventMarker[];
  activeDate: string;
}

const EVENT_STYLE: Record<EventMarker['type'], { Icon: LucideIcon; tone: string; label: string }> = {
  rain: { Icon: CloudRain, tone: 'bg-rain-100 text-rain-600 ring-rain-200', label: 'Rain' },
  heat: { Icon: Thermometer, tone: 'bg-stress-100 text-stress-600 ring-stress-300/60', label: 'Heat' },
  dry: { Icon: Sun, tone: 'bg-sun-100 text-sun-700 ring-sun-300/60', label: 'Dry spell' },
  recovery: { Icon: Sprout, tone: 'bg-leaf-100 text-leaf-700 ring-leaf-200', label: 'Recovery' },
  management: { Icon: Tractor, tone: 'bg-mist text-ink-soft ring-line-strong', label: 'Management' },
};

const MONTHS = [
  { label: 'Jun', date: '2026-06-01' },
  { label: 'Jul', date: '2026-07-01' },
  { label: 'Aug', date: '2026-08-01' },
  { label: 'Sep', date: '2026-09-01' },
];

export function CropDevelopment({ fieldKey, timeline, events, activeDate }: CropDevelopmentProps) {
  const reduce = useReducedMotion();
  const isMobile = useIsMobile();
  const [signal, setSignal] = useState<Signal>('ndvi');
  const [hover, setHover] = useState<number | null>(null);
  const [openEvent, setOpenEvent] = useState<string | null>(null);
  const [wrapRef, width] = useElementWidth<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');

  const plotHeight = isMobile ? 170 : 236;
  const margin = { top: 12, right: 10, bottom: 66, left: 34 };
  const height = margin.top + plotHeight + margin.bottom;
  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;

  const geo = useMemo(() => {
    if (width <= 0 || timeline.length < 2) return null;
    const times = timeline.map((o) => toTime(o.date));
    const x0 = margin.left + 6;
    const x1 = width - margin.right - 6;
    const sx = scaleLinear(times[0], times[times.length - 1], x0, x1);
    const bottom = margin.top + plotHeight;
    const sy = scaleLinear(0, 1, bottom, margin.top);
    const series = (key: 'ndvi' | 'ndre' | 'regionalBaselineNdvi') =>
      timeline.map((o, i) => ({ x: sx(times[i]), y: sy(o[key]) }));
    return {
      sx,
      x0,
      x1,
      bottom,
      times,
      points: { ndvi: series('ndvi'), ndre: series('ndre') },
      paths: { ndvi: monotonePath(series('ndvi')), ndre: monotonePath(series('ndre')) },
      baseline: monotonePath(series('regionalBaselineNdvi')),
      ticks: [0.2, 0.4, 0.6, 0.8].map((v) => ({ v, y: sy(v) })),
      months: MONTHS.map((m) => ({ ...m, x: sx(toTime(m.date)) })).filter((m) => m.x > x0 + 8 && m.x < x1 - 8),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeline, width, plotHeight]);

  const activeTime = toTime(activeDate);
  const activeX = geo ? Math.max(geo.x0, Math.min(geo.x1, geo.sx(activeTime))) : 0;
  const points = geo ? geo.points[signal] : [];
  const hovered = hover !== null && geo ? hover : null;

  const onPointerMove = (event: PointerEvent<SVGRectElement>) => {
    if (!geo || !svgRef.current || event.pointerType !== 'mouse') return;
    const rect = svgRef.current.getBoundingClientRect();
    setHover(
      nearestIndex(
        points.map((p) => p.x),
        event.clientX - rect.left,
      ),
    );
  };

  const eventsInRange = geo
    ? events
        .map((e) => ({ ...e, x: geo.sx(toTime(e.date)) }))
        .filter((e) => e.x >= geo.x0 - 1 && e.x <= geo.x1 + 1)
    : [];

  const label = signal.toUpperCase();

  return (
    <section className="flex h-full flex-col rounded-2xl border border-line bg-surface transition-colors duration-300 hover:border-line-strong p-5 sm:p-6" aria-labelledby={`crop-${uid}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id={`crop-${uid}`} className="text-[16px] font-semibold tracking-[-0.01em] text-ink">
            Crop development
          </h2>
          <p className="mt-1 text-[14px] text-muted">Canopy vigor from multispectral observations, with season events.</p>
        </div>
        <SegmentedControl
          ariaLabel="Vegetation index"
          size="sm"
          mono
          value={signal}
          onChange={setSignal}
          options={[
            { value: 'ndvi', label: 'NDVI' },
            { value: 'ndre', label: 'NDRE' },
          ]}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-[2px] w-4 rounded-full bg-leaf-700" aria-hidden="true" />
          Observed <span className="data">{label}</span>
        </span>
        <AnimatePresence initial={false}>
          {signal === 'ndvi' && (
            <motion.span
              className="inline-flex items-center gap-1.5"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              <span className="h-[2px] w-4 rounded-full bg-[#B4BAC2]" aria-hidden="true" />
              {APP_CONFIG.demoMode ? '5-yr regional baseline' : 'Site average, same image'}
            </motion.span>
          )}
        </AnimatePresence>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full border-2 border-surface bg-leaf-700 ring-1 ring-leaf-700/30" aria-hidden="true" />
          Satellite observation
        </span>
      </div>

      <div ref={wrapRef} className="relative mt-3" style={{ height }}>
        {geo && (
          <svg
            ref={svgRef}
            width={width}
            height={height}
            className="overflow-visible"
            role="img"
            aria-label={`${label} through the season, observed up to the selected forecast date.`}
          >
            <defs>
              <clipPath id={`veg-past-${uid}`}>
                <motion.rect x={0} y={0} height={height} initial={false} animate={{ width: activeX }} transition={transition} />
              </clipPath>
            </defs>
            {geo.ticks.map((t) => (
              <g key={t.v}>
                <line x1={margin.left} x2={width - margin.right} y1={t.y} y2={t.y} stroke={C.line} />
                <text x={margin.left - 8} y={t.y + 4} textAnchor="end" className="data fill-faint text-[10.5px] tabular-nums">
                  {t.v.toFixed(1)}
                </text>
              </g>
            ))}
            <line x1={margin.left} x2={width - margin.right} y1={geo.bottom} y2={geo.bottom} stroke={C.lineStrong} />
            {geo.months.map((m) => (
              <text key={m.label} x={m.x} y={geo.bottom + 56} textAnchor="middle" className="data fill-faint text-[11px]">
                {m.label}
              </text>
            ))}

            <motion.path
              d={geo.baseline}
              fill="none"
              stroke="#B4BAC2"
              strokeWidth={1.5}
              strokeLinecap="round"
              initial={false}
              animate={{ opacity: signal === 'ndvi' ? 1 : 0 }}
              transition={{ duration: 0.25 }}
            />

            <g key={fieldKey}>
              <motion.path
                fill="none"
                stroke={C.leaf200}
                strokeWidth={2}
                strokeLinecap="round"
                initial={reduce ? false : { d: geo.paths[signal], pathLength: 0, opacity: 0 }}
                animate={{ d: geo.paths[signal], pathLength: 1, opacity: 1 }}
                transition={{ d: transition, pathLength: { duration: reduce ? 0 : 0.9, ease: EASE_OUT }, opacity: { duration: 0.05 } }}
              />
              <g clipPath={`url(#veg-past-${uid})`}>
                <motion.path
                  fill="none"
                  stroke={C.leaf700}
                  strokeWidth={2.5}
                  strokeLinecap="round"
                  initial={reduce ? false : { d: geo.paths[signal], pathLength: 0, opacity: 0 }}
                  animate={{ d: geo.paths[signal], pathLength: 1, opacity: 1 }}
                  transition={{ d: transition, pathLength: { duration: reduce ? 0 : 0.9, ease: EASE_OUT }, opacity: { duration: 0.05 } }}
                />
              </g>
              {points.map((p, i) => {
                const observed = geo.times[i] <= activeTime;
                return (
                  <motion.circle
                    key={i}
                    cx={p.x}
                    stroke={C.surface}
                    strokeWidth={2}
                    initial={false}
                    animate={{ cy: p.y, r: hovered === i ? 5 : 3.5, fill: observed ? C.leaf700 : C.leaf200 }}
                    transition={transition}
                  />
                );
              })}
            </g>

            <motion.line
              y1={margin.top}
              y2={geo.bottom}
              stroke={C.leaf700}
              strokeOpacity={0.32}
              initial={false}
              animate={{ x1: activeX, x2: activeX }}
              transition={transition}
            />

            {/* Event lane: a hairline tick anchors each event to its date on the curve. */}
            {eventsInRange.map((e) => (
              <line
                key={e.date}
                x1={e.x}
                x2={e.x}
                y1={margin.top + 4}
                y2={geo.bottom + 16}
                stroke={C.faint}
                strokeOpacity={toTime(e.date) <= activeTime ? 0.35 : 0.15}
                strokeDasharray="2 3"
              />
            ))}

            {hovered !== null && (
              <line x1={points[hovered].x} x2={points[hovered].x} y1={margin.top} y2={geo.bottom} stroke={C.faint} strokeOpacity={0.45} />
            )}

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

        {/* Event markers are real buttons so they work with keyboard and touch. */}
        {geo &&
          eventsInRange.map((e) => {
            const style = EVENT_STYLE[e.type];
            const happened = toTime(e.date) <= activeTime;
            const isOpen = openEvent === e.date;
            const flip = e.x > width - 150;
            const Icon = style.Icon;
            return (
              <div key={e.date} className="absolute" style={{ left: e.x, top: geo.bottom + 18 }}>
                <button
                  type="button"
                  aria-label={`${e.displayDate}: ${e.title}. ${e.summary}`}
                  aria-expanded={isOpen}
                  onMouseEnter={() => setOpenEvent(e.date)}
                  onMouseLeave={() => setOpenEvent((cur) => (cur === e.date ? null : cur))}
                  onFocus={() => setOpenEvent(e.date)}
                  onBlur={() => setOpenEvent((cur) => (cur === e.date ? null : cur))}
                  onClick={() => setOpenEvent((cur) => (cur === e.date ? null : e.date))}
                  className={`-ml-[11px] flex h-[22px] w-[22px] items-center justify-center rounded-full ring-1 transition-[opacity,transform] duration-300 hover:scale-110 ${style.tone} ${
                    happened ? 'opacity-100' : 'opacity-45'
                  }`}
                >
                  <Icon className="h-3 w-3" strokeWidth={2.2} />
                </button>
                <AnimatePresence>
                  {isOpen && (
                    <motion.div
                      role="tooltip"
                      className={`pointer-events-none absolute bottom-full z-20 mb-2 w-56 rounded-xl border border-line bg-surface p-3 shadow-lift ${
                        flip ? 'right-0 -mr-[11px]' : '-ml-[11px] left-0'
                      }`}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 4, transition: { duration: 0.1 } }}
                      transition={{ duration: 0.16, ease: EASE_OUT }}
                    >
                      <div className="flex items-center justify-between gap-2 text-[12px]">
                        <span className="data font-medium text-ink">{e.displayDate}</span>
                        <span className="text-muted">{happened ? style.label : `${style.label} · later in season`}</span>
                      </div>
                      <div className="mt-1 text-[13px] font-medium text-ink">{e.title}</div>
                      <p className="mt-1 text-[12px] leading-relaxed text-muted">{e.hoverDetail.replace(/^[^:]{3,48}:\s*/, '')}</p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}

        <AnimatePresence>
          {geo && hovered !== null && (
            <motion.div
              className="pointer-events-none absolute top-0 left-0 z-10 w-44 rounded-xl border border-line bg-surface/95 px-3 py-2.5 shadow-lift backdrop-blur-sm"
              initial={{ opacity: 0, x: points[hovered].x + (points[hovered].x > width - 200 ? -190 : 12), y: 8 }}
              animate={{ opacity: 1, x: points[hovered].x + (points[hovered].x > width - 200 ? -190 : 12), y: 8 }}
              exit={{ opacity: 0, transition: { duration: 0.1 } }}
              transition={{ type: 'spring', stiffness: 520, damping: 42, mass: 0.6, opacity: { duration: 0.15 } }}
            >
              <div className="flex items-baseline justify-between text-[12px]">
                <span className="data font-medium text-ink">{timeline[hovered].displayDate}</span>
                <span className="text-muted">
                  {geo.times[hovered] <= activeTime ? 'Observed' : 'Later in season'}
                </span>
              </div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="data text-[12px] text-muted">{label}</span>
                <span className="data-tight text-[20px] font-medium text-ink">{timeline[hovered][signal].toFixed(2)}</span>
              </div>
              {signal === 'ndvi' && (
                <div className="mt-1 flex justify-between text-[12px] text-muted">
                  <span>Regional baseline</span>
                  <span className="data">{timeline[hovered].regionalBaselineNdvi.toFixed(2)}</span>
                </div>
              )}
              <div className="mt-1.5 border-t border-line pt-1.5 text-[11px] text-faint">Satellite observation</div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}
