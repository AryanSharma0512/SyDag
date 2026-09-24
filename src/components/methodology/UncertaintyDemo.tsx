import { useMemo, useState, type PointerEvent } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import type { FieldForecast } from '../../types/agricultural';
import { APP_CONFIG } from '../../config/appConfig';
import { bandPath, monotonePath, nearestIndex, scaleLinear, toTime } from '../../utils/chart';
import { DATA_TRANSITION } from '../../utils/motion';
import { useElementWidth, useIsMobile } from '../../utils/hooks';
import { PALETTE as C } from '../../utils/palette';
import { formatYield } from '../../utils/formatters';

const PHASES = [
  { key: 'early', label: 'Early season', note: 'Few observations yet. The model leans on soil and history, so the range is wide.' },
  { key: 'mid', label: 'Mid season', note: 'Canopy vigor and pollination weather are now visible. The range narrows quickly.' },
  { key: 'late', label: 'Late season', note: 'Most of the yield is already set. The range is narrow and stable.' },
] as const;

/** Sampled bell curve lying on its side: wide intervals are flat, narrow intervals are tall. */
function bellPath(x: number, y: number, sigmaPx: number, peakScale: number) {
  const pts: string[] = [];
  const samples = 28;
  for (let i = 0; i <= samples; i++) {
    const t = -3 + (6 * i) / samples;
    const py = y + t * sigmaPx;
    const px = x + peakScale * Math.exp(-0.5 * t * t);
    pts.push(`${i === 0 ? 'M' : 'L'}${px.toFixed(1)},${py.toFixed(1)}`);
  }
  return `${pts.join('')}L${x},${(y + 3 * sigmaPx).toFixed(1)}L${x},${(y - 3 * sigmaPx).toFixed(1)}Z`;
}

/**
 * Explains prediction intervals by comparison instead of paragraphs: early
 * forecasts carry a wide range, late ones a narrow range. Hover the chart or
 * the phase buttons to compare.
 */
export function UncertaintyDemo({ forecast }: { forecast: FieldForecast }) {
  const reduce = useReducedMotion();
  const isMobile = useIsMobile();
  const [probe, setProbe] = useState(0);
  const [wrapRef, width] = useElementWidth<HTMLDivElement>();

  const snaps = forecast.snapshots;
  const phaseIndex = snaps.length ? [0, Math.min(APP_CONFIG.defaultDateIndex, snaps.length - 1), snaps.length - 1] : [0, 0, 0];
  const height = isMobile ? 240 : 290;
  const margin = { top: 24, right: isMobile ? 70 : 110, bottom: 34, left: 40 };

  const geo = useMemo(() => {
    if (!snaps.length || width <= 0) return null;
    const times = snaps.map((s) => toTime(s.date));
    const sx = scaleLinear(times[0], times[times.length - 1], margin.left + 8, width - margin.right);
    const sy = scaleLinear(120, 205, height - margin.bottom, margin.top);
    const mid = snaps.map((s, i) => ({ x: sx(times[i]), y: sy(s.yield) }));
    const hi = snaps.map((s, i) => ({ x: sx(times[i]), y: sy(s.upperBound) }));
    const lo = snaps.map((s, i) => ({ x: sx(times[i]), y: sy(s.lowerBound) }));
    return { sy, mid, hi, lo, line: monotonePath(mid), band: bandPath(hi, lo) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snaps, width, height]);

  const s = snaps[probe];
  const phase = probe <= 1 ? PHASES[0] : probe >= snaps.length - 2 ? PHASES[2] : PHASES[1];
  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;

  let bell = '';
  let bracket = { x: 0, top: 0, bottom: 0, center: 0 };
  if (geo && s) {
    const p = geo.mid[probe];
    const top = geo.hi[probe].y;
    const bottom = geo.lo[probe].y;
    const sigma = (bottom - top) / (2 * 1.645);
    // Constant probability mass: a narrower interval means a taller peak.
    const peak = Math.min(isMobile ? 60 : 88, (isMobile ? 520 : 760) / Math.max(4, sigma));
    bell = bellPath(p.x + 14, p.y, sigma, peak);
    bracket = { x: p.x, top, bottom, center: p.y };
  }

  const onPointerMove = (event: PointerEvent<SVGRectElement>) => {
    if (!geo) return;
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!rect) return;
    setProbe(
      nearestIndex(
        geo.mid.map((p) => p.x),
        event.clientX - rect.left,
      ),
    );
  };

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px] lg:gap-12">
      <div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Compare forecast phases">
          {PHASES.map((ph, i) => {
            const active = phase.key === ph.key;
            return (
              <button
                key={ph.key}
                type="button"
                aria-pressed={active}
                onMouseEnter={() => setProbe(phaseIndex[i])}
                onFocus={() => setProbe(phaseIndex[i])}
                onClick={() => setProbe(phaseIndex[i])}
                className={`rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-colors duration-150 ${
                  active ? 'border-leaf-700 bg-leaf-700 text-white' : 'border-line-strong bg-surface text-ink-soft hover:border-faint'
                }`}
              >
                {ph.label}
              </button>
            );
          })}
        </div>

        <div ref={wrapRef} className="relative mt-5" style={{ height }}>
          {geo && s && (
            <svg width={width} height={height} className="overflow-visible" role="img" aria-label={`On ${s.displayDate}, the 90% range is ${formatYield(s.lowerBound)} to ${formatYield(s.upperBound)} bushels per acre.`}>
              {[140, 160, 180, 200].map((v) => (
                <g key={v}>
                  <line x1={margin.left} x2={width - margin.right + 40} y1={geo.sy(v)} y2={geo.sy(v)} stroke={C.line} />
                  <text x={margin.left - 8} y={geo.sy(v) + 4} textAnchor="end" className="data fill-faint text-[10.5px]">
                    {v}
                  </text>
                </g>
              ))}
              <path d={geo.band} fill={C.leaf400} opacity={0.12} />
              <path d={geo.line} fill="none" stroke={C.leaf700} strokeWidth={2.2} strokeLinecap="round" />
              {geo.mid.map((p, i) => (
                <circle key={i} cx={p.x} cy={p.y} r={i === probe ? 0 : 3} fill={C.leaf300} stroke={C.surface} strokeWidth={1.5} />
              ))}

              {/* Probe: the interval at the chosen date, and the distribution it implies. */}
              <motion.path
                fill={C.leaf400}
                fillOpacity={0.22}
                stroke={C.leaf700}
                strokeOpacity={0.5}
                strokeWidth={1.2}
                initial={false}
                animate={{ d: bell }}
                transition={transition}
              />
              <motion.g initial={false} animate={{ x: bracket.x }} transition={transition}>
                <motion.line
                  x1={0}
                  x2={0}
                  stroke={C.leaf700}
                  strokeWidth={2}
                  strokeLinecap="round"
                  initial={false}
                  animate={{ y1: bracket.top, y2: bracket.bottom }}
                  transition={transition}
                />
                {[bracket.top, bracket.bottom].map((y, k) => (
                  <motion.line key={k} x1={-6} x2={6} stroke={C.leaf700} strokeWidth={2} strokeLinecap="round" initial={false} animate={{ y1: y, y2: y }} transition={transition} />
                ))}
                <motion.circle r={5.5} fill={C.leaf700} stroke={C.surface} strokeWidth={2.5} initial={false} animate={{ cy: bracket.center }} transition={transition} />
              </motion.g>

              {geo.mid.map((p, i) =>
                i === 0 || i === geo.mid.length - 1 || i === probe ? (
                  <text key={i} x={p.x} y={height - 10} textAnchor="middle" className={`data text-[11px] ${i === probe ? 'fill-ink font-medium' : 'fill-faint'}`}>
                    {snaps[i].displayDate}
                  </text>
                ) : null,
              )}

              <rect
                x={margin.left}
                y={0}
                width={Math.max(0, width - margin.left - margin.right + 30)}
                height={height}
                fill="transparent"
                style={{ touchAction: 'pan-y' }}
                onPointerMove={onPointerMove}
                onPointerDown={onPointerMove}
              />
            </svg>
          )}
        </div>
      </div>

      <div className="flex flex-col justify-center border-t border-line pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-10" aria-live="polite">
        {s && (
          <>
            <div className="text-[13px] text-muted">
              {phase.label} · <span className="data">{s.displayDate}</span>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="data-tight text-[40px] leading-none font-medium text-ink">
                ±{((s.upperBound - s.lowerBound) / 2).toFixed(1)}
              </span>
              <span className="data text-[13px] text-muted">bu/ac</span>
            </div>
            <p className="mt-3 text-[14px] text-ink-soft">
              90% of outcomes expected between <span className="data">{formatYield(s.lowerBound)}</span> and{' '}
              <span className="data">{formatYield(s.upperBound)}</span> bu/ac.
            </p>
            <p className="mt-3 text-[14px] leading-relaxed text-muted">{phase.note}</p>
            <p className="mt-5 text-[12px] text-faint">Demo field: {forecast.field.name}</p>
          </>
        )}
      </div>
    </div>
  );
}
