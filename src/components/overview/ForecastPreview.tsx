import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, useInView, useReducedMotion } from 'motion/react';
import { ArrowRight } from 'lucide-react';
import type { FieldForecast } from '../../types/agricultural';
import { getForecast } from '../../services/forecasts';
import { getFields, pickDefaultFieldId } from '../../services/fields';
import { getDatasetLabel } from '../../services/dataset';
import { APP_CONFIG } from '../../config/appConfig';
import { bandPath, monotonePath, scaleLinear, toTime } from '../../utils/chart';
import { EASE_OUT } from '../../utils/motion';
import { useElementWidth } from '../../utils/hooks';
import { PALETTE as C } from '../../utils/palette';
import { ratingLabel, shortCropName } from '../../utils/formatters';
import { Link } from '../../utils/router';

const INPUTS = [
  { label: 'Satellite imagery', color: C.leaf500 },
  { label: 'Field record', color: C.inkSoft },
  { label: 'Weather & soil', color: C.rain500 },
];

/**
 * The scroll hand-off from the hero: the three inputs lead into a preview of one
 * plot's forecast, whose line then draws itself.
 */
export function ForecastPreview() {
  const [forecast, setForecast] = useState<FieldForecast | null>(null);
  const [datasetLabel, setDatasetLabel] = useState(APP_CONFIG.demoMode ? APP_CONFIG.datasetLabel : '');
  const reduce = useReducedMotion();
  const sectionRef = useRef<HTMLDivElement>(null);
  const inView = useInView(sectionRef, { once: true, margin: '0px 0px -18% 0px' });
  const [linesRef, linesWidth] = useElementWidth<HTMLDivElement>();
  const shown = inView || !!reduce;

  useEffect(() => {
    let active = true;
    getFields()
      .then((fields) => {
        const id = pickDefaultFieldId(fields);
        return id ? getForecast(id) : null;
      })
      .then((data) => {
        if (active && data) setForecast(data);
      })
      .catch(() => undefined);
    getDatasetLabel()
      .then((label) => active && setDatasetLabel(label))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const lineHeight = 112;
  const converge = useMemo(() => {
    const w = Math.max(linesWidth, 1);
    const target = { x: w / 2, y: lineHeight };
    return INPUTS.map((input, i) => {
      const x = (w * (i * 2 + 1)) / 6;
      return {
        ...input,
        d: `M${x},0 C${x},${lineHeight * 0.55} ${target.x},${lineHeight * 0.45} ${target.x},${lineHeight}`,
      };
    });
  }, [linesWidth]);

  const snapshot = forecast?.snapshots[Math.min(APP_CONFIG.defaultDateIndex, (forecast?.snapshots.length ?? 1) - 1)];

  return (
    <section className="mx-auto max-w-6xl px-4 pt-10 pb-8 sm:px-6 sm:pt-16 sm:pb-10" aria-labelledby="preview-heading">
      <div ref={sectionRef} className="mx-auto max-w-3xl text-center">
        <motion.p
          className="text-[13px] font-medium text-leaf-700"
          initial={reduce ? false : { opacity: 0, y: 8 }}
          animate={shown ? { opacity: 1, y: 0 } : undefined}
          transition={{ duration: 0.5, ease: EASE_OUT }}
        >
          One plot through the season
        </motion.p>
        <motion.h2
          id="preview-heading"
          className="mt-3 text-[28px] leading-tight font-semibold tracking-[-0.025em] text-balance text-ink sm:text-[36px]"
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={shown ? { opacity: 1, y: 0 } : undefined}
          transition={{ duration: 0.6, ease: EASE_OUT, delay: 0.05 }}
        >
          The forecast updates as new imagery arrives.
        </motion.h2>
        <motion.p
          className="mx-auto mt-4 max-w-xl text-[16px] leading-relaxed text-pretty text-muted"
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={shown ? { opacity: 1, y: 0 } : undefined}
          transition={{ duration: 0.6, ease: EASE_OUT, delay: 0.1 }}
        >
          The line is the predicted final yield and the band is its 90% range. Each point uses only the imagery and
          records available by that date.
        </motion.p>
      </div>

      <div className="mx-auto mt-12 max-w-4xl">
        {/* Converging inputs */}
        <div className="grid grid-cols-3 text-center">
          {INPUTS.map((input, i) => (
            <motion.div
              key={input.label}
              className="flex items-center justify-center gap-2 px-1 text-[12px] font-medium text-ink-soft sm:text-[13px]"
              initial={reduce ? false : { opacity: 0, y: 6 }}
              animate={shown ? { opacity: 1, y: 0 } : undefined}
              transition={{ duration: 0.45, ease: EASE_OUT, delay: 0.2 + i * 0.08 }}
            >
              <span className="h-[2px] w-3 rounded-full" style={{ background: input.color }} aria-hidden="true" />
              {input.label}
            </motion.div>
          ))}
        </div>
        <div ref={linesRef} className="mt-3 h-[112px]" aria-hidden="true">
          {linesWidth > 0 && (
            <svg width={linesWidth} height={lineHeight} className="overflow-visible">
              {converge.map((line, i) => (
                <g key={line.label}>
                  <path d={line.d} fill="none" stroke={C.line} strokeWidth={1.5} />
                  <motion.path
                    d={line.d}
                    fill="none"
                    stroke={line.color}
                    strokeWidth={1.6}
                    strokeLinecap="round"
                    initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                    animate={shown ? { pathLength: 1, opacity: 0.9 } : undefined}
                    transition={{
                      pathLength: { duration: 0.9, ease: EASE_OUT, delay: 0.35 + i * 0.1 },
                      opacity: { duration: 0.1, delay: 0.35 + i * 0.1 },
                    }}
                  />
                  {!reduce && (
                    <motion.path
                      d={line.d}
                      pathLength={100}
                      fill="none"
                      stroke={line.color}
                      strokeWidth={3.2}
                      strokeLinecap="round"
                      strokeDasharray="5 100"
                      initial={{ strokeDashoffset: 105, opacity: 0 }}
                      animate={shown ? { strokeDashoffset: 0, opacity: [0, 1, 1, 0] } : undefined}
                      transition={{ duration: 1.1, ease: 'easeInOut', delay: 0.9 + i * 0.12 }}
                    />
                  )}
                </g>
              ))}
              <motion.circle
                cx={linesWidth / 2}
                cy={lineHeight}
                r={5}
                fill={C.leaf700}
                stroke={C.canvas}
                strokeWidth={3}
                initial={reduce ? false : { scale: 0 }}
                animate={shown ? { scale: 1 } : undefined}
                transition={{ duration: 0.35, ease: [0.34, 1.56, 0.64, 1], delay: 1.35 }}
              />
            </svg>
          )}
        </div>

        {/* Dashboard preview card */}
        <motion.div
          className="relative mt-2 rounded-2xl border border-line bg-surface p-5 shadow-float sm:p-7"
          initial={reduce ? false : { opacity: 0, y: 24, scale: 0.98 }}
          animate={shown ? { opacity: 1, y: 0, scale: 1 } : undefined}
          transition={{ duration: 0.7, ease: EASE_OUT, delay: 1.25 }}
        >
          {forecast && snapshot ? (
            <>
              <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
                <div className="flex items-baseline gap-3">
                  <span className="text-[16px] font-semibold tracking-tight text-ink">{forecast.field.name}</span>
                  <span className="text-[14px] text-muted">
                    {shortCropName(forecast.field.crop)} · <span className="data">{forecast.field.season}</span>
                  </span>
                </div>
                <span className="data text-[14px] text-ink-soft">{snapshot.displayDate}</span>
              </div>
              <div className="mt-5 grid grid-cols-3 divide-x divide-line">
                <PreviewMetric value={snapshot.yield.toFixed(1)} unit="bu/ac" label="Predicted yield" />
                <PreviewMetric
                  value={`${Math.round(snapshot.lowerBound)}–${Math.round(snapshot.upperBound)}`}
                  unit="bu/ac"
                  label="90% range"
                />
                <PreviewMetric value={`${snapshot.confidence}%`} unit="confidence" label={ratingLabel(snapshot.confidenceRating)} />
              </div>
              <PreviewChart forecast={forecast} activeIndex={APP_CONFIG.defaultDateIndex} play={shown} />
              <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
                <span className="text-[13px] text-muted">
                  {datasetLabel}<span className="hidden sm:inline"> · {forecast.field.location}</span>
                </span>
                <Link
                  to="dashboard"
                  className="group inline-flex items-center gap-1.5 text-[14px] font-medium text-leaf-700 hover:text-leaf-800"
                >
                  Review plots
                  <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
                </Link>
              </div>
            </>
          ) : (
            <div className="h-[340px]" />
          )}
        </motion.div>
      </div>
    </section>
  );
}

function PreviewMetric({ value, unit, label }: { value: string; unit: string; label: string }) {
  return (
    <div className="px-2.5 first:pl-0 sm:px-6">
      <div className="data-tight text-[19px] leading-none font-medium whitespace-nowrap text-ink sm:text-[30px]">{value}</div>
      <div className="data mt-1.5 text-[12px] text-muted">{unit}</div>
      <div className="mt-2 hidden text-[13px] text-muted sm:block">{label}</div>
    </div>
  );
}

function PreviewChart({ forecast, activeIndex, play }: { forecast: FieldForecast; activeIndex: number; play: boolean }) {
  const reduce = useReducedMotion();
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const height = 170;
  const pad = { top: 12, right: 8, bottom: 24, left: 8 };

  const geo = useMemo(() => {
    if (width <= 0) return null;
    const snaps = forecast.snapshots;
    const times = snaps.map((s) => toTime(s.date));
    const x = scaleLinear(times[0], times[times.length - 1], pad.left, width - pad.right);
    const lo = Math.min(...snaps.map((s) => s.lowerBound));
    const hi = Math.max(...snaps.map((s) => s.upperBound));
    const y = scaleLinear(lo - 6, hi + 6, height - pad.bottom, pad.top);
    const mid = snaps.map((s, i) => ({ x: x(times[i]), y: y(s.yield) }));
    const up = snaps.map((s, i) => ({ x: x(times[i]), y: y(s.upperBound) }));
    const low = snaps.map((s, i) => ({ x: x(times[i]), y: y(s.lowerBound) }));
    const index = Math.min(activeIndex, snaps.length - 1);
    return {
      line: monotonePath(mid),
      band: bandPath(up, low),
      bandCollapsed: bandPath(mid, mid),
      active: mid[index],
      activeX: mid[index].x,
      first: { x: mid[0].x, label: snaps[0].displayDate },
      last: { x: mid[mid.length - 1].x, label: snaps[snaps.length - 1].displayDate },
      activeLabel: snaps[index].displayDate,
      // The first and last labels step aside when the active date is one of them.
      activeAt: index === 0 ? 'first' : index === snaps.length - 1 ? 'last' : 'middle',
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forecast, width, activeIndex]);

  const clipId = 'preview-past';

  return (
    <div ref={ref} className="mt-6" aria-hidden="true">
      {geo && (
        <svg width={width} height={height} className="overflow-visible">
          <defs>
            <clipPath id={clipId}>
              <rect x={0} y={0} width={geo.activeX} height={height} />
            </clipPath>
          </defs>
          {[0.25, 0.5, 0.75].map((k) => (
            <line
              key={k}
              x1={pad.left}
              x2={width - pad.right}
              y1={pad.top + (height - pad.top - pad.bottom) * k}
              y2={pad.top + (height - pad.top - pad.bottom) * k}
              stroke={C.line}
            />
          ))}
          <motion.path
            fill={C.leaf400}
            initial={reduce ? false : { d: geo.bandCollapsed, opacity: 0 }}
            animate={play ? { d: geo.band, opacity: 0.12 } : undefined}
            transition={{ duration: 0.8, ease: EASE_OUT, delay: 1.7 }}
          />
          <motion.path
            d={geo.line}
            fill="none"
            stroke={C.leaf300}
            strokeWidth={2}
            strokeLinecap="round"
            initial={reduce ? false : { pathLength: 0, opacity: 0 }}
            animate={play ? { pathLength: 1, opacity: 1 } : undefined}
            transition={{ pathLength: { duration: 1, ease: EASE_OUT, delay: 1.55 }, opacity: { duration: 0.05, delay: 1.55 } }}
          />
          <g clipPath={`url(#${clipId})`}>
            <motion.path
              d={geo.line}
              fill="none"
              stroke={C.leaf700}
              strokeWidth={2.5}
              strokeLinecap="round"
              initial={reduce ? false : { pathLength: 0, opacity: 0 }}
              animate={play ? { pathLength: 1, opacity: 1 } : undefined}
              transition={{ pathLength: { duration: 1, ease: EASE_OUT, delay: 1.55 }, opacity: { duration: 0.05, delay: 1.55 } }}
            />
          </g>
          <motion.line
            x1={geo.activeX}
            x2={geo.activeX}
            y1={pad.top - 4}
            y2={height - pad.bottom}
            stroke={C.leaf700}
            strokeOpacity={0.3}
            initial={reduce ? false : { opacity: 0 }}
            animate={play ? { opacity: 1 } : undefined}
            transition={{ duration: 0.4, delay: 2.2 }}
          />
          <motion.circle
            cx={geo.active.x}
            cy={geo.active.y}
            r={5.5}
            fill={C.leaf700}
            stroke={C.surface}
            strokeWidth={2.5}
            initial={reduce ? false : { scale: 0 }}
            animate={play ? { scale: 1 } : undefined}
            transition={{ duration: 0.4, ease: [0.34, 1.56, 0.64, 1], delay: 2.25 }}
          />
          {geo.activeAt !== 'first' && (
            <text x={geo.first.x} y={height - 4} className="data fill-faint text-[11px]">
              {geo.first.label}
            </text>
          )}
          <text
            x={geo.activeX}
            y={height - 4}
            textAnchor={geo.activeAt === 'first' ? 'start' : geo.activeAt === 'last' ? 'end' : 'middle'}
            className="data fill-ink-soft text-[11px]"
          >
            {geo.activeLabel}
          </text>
          {geo.activeAt !== 'last' && (
            <text x={geo.last.x} y={height - 4} textAnchor="end" className="data fill-faint text-[11px]">
              {geo.last.label}
            </text>
          )}
        </svg>
      )}
    </div>
  );
}
