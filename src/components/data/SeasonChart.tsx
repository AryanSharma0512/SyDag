import { useState, type KeyboardEvent } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { useElementWidth } from '../../utils/hooks';
import { DATA_TRANSITION } from '../../utils/motion';
import { monotonePath, niceTicks, scaleLinear } from '../../utils/chart';
import { formatNumber } from '../../utils/formatters';

export interface ChartSeries {
  id: string;
  label: string;
  color: string;
  values: Array<number | null>;
}

interface SeasonChartProps {
  /** One category per forecast date, e.g. "Jul 22". */
  labels: string[];
  series: ChartSeries[];
  /**
   * bars: side by side. nested: every later series drawn inside the first (for a
   * part of a whole, like 7-day rain within 30-day rain). line: one line per series.
   */
  kind: 'bars' | 'nested' | 'line';
  unit: string;
  decimals?: number;
  /** A row of text values under the x axis, e.g. data completeness per date. */
  footer?: { label: string; values: string[] };
  ariaLabel: string;
}

const HEIGHT = 220;
const M = { top: 12, right: 8, bottom: 26 };
const FOOTER_ROW = 20;

/** Rectangle with rounded top corners, anchored to the baseline. */
function barPath(x: number, y: number, w: number, h: number): string {
  if (h <= 0 || w <= 0) return `M${x},${y}h${w}v0h${-w}Z`;
  const r = Math.min(3, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function domain(series: ChartSeries[], zeroBased: boolean): number[] {
  const values = series.flatMap((s) => s.values).filter((v): v is number => v !== null);
  if (!values.length) return [0, 1];
  const hi = Math.max(...values);
  const lo = zeroBased ? 0 : Math.min(...values);
  const pad = zeroBased ? 0 : Math.max(1, (hi - lo) * 0.15);
  const ticks = niceTicks(Math.max(zeroBased ? 0 : -Infinity, lo - pad), hi + pad || 1, 4);
  const step = ticks.length > 1 ? ticks[1] - ticks[0] : 1;
  while (ticks[ticks.length - 1] < hi) ticks.push(ticks[ticks.length - 1] + step);
  if (!zeroBased && ticks[0] > lo) ticks.unshift(ticks[0] - step);
  return ticks;
}

/**
 * A small category chart over the season's forecast dates. The readout above the
 * plot doubles as the legend: it names every series and shows its value at the
 * hovered (or latest) date. Values come straight from the backend; nothing is
 * recalculated here.
 */
export function SeasonChart({ labels, series, kind, unit, decimals = 0, footer, ariaLabel }: SeasonChartProps) {
  const reduce = useReducedMotion();
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const n = labels.length;
  const active = hover ?? n - 1;
  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;

  const height = HEIGHT + (footer ? FOOTER_ROW : 0);
  const left = footer ? 68 : 44; // room for the footer row's label
  const plotBottom = HEIGHT - M.bottom;
  const innerW = Math.max(0, width - left - M.right);
  const band = n ? innerW / n : 0;
  const cx = (i: number) => left + band * (i + 0.5);
  const ticks = domain(series, kind !== 'line');
  const y = scaleLinear(ticks[0], ticks[ticks.length - 1], plotBottom, M.top);
  const labelEvery = Math.max(1, Math.ceil((n * 46) / Math.max(innerW, 1)));
  const barW = Math.min(kind === 'bars' ? 44 : 34, band * 0.62);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowRight') setHover(Math.min(n - 1, active + 1));
    else if (event.key === 'ArrowLeft') setHover(Math.max(0, active - 1));
    else return;
    event.preventDefault();
    event.stopPropagation();
  };

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1.5" aria-live="polite">
        <span className="data w-14 text-[13px] font-medium text-ink">{labels[active]}</span>
        {series.map((s) => {
          const value = s.values[active];
          return (
            <span key={s.id} className="inline-flex items-baseline gap-2">
              <span
                className={`inline-block shrink-0 self-center ${kind === 'line' ? 'h-[2px] w-3.5 rounded-full' : 'h-2.5 w-2.5 rounded-[3px]'}`}
                style={{ backgroundColor: s.color }}
                aria-hidden="true"
              />
              <span className="data text-[15px] font-medium text-ink tabular-nums">
                {value === null ? '—' : formatNumber(value, decimals)}
                {value !== null && unit && <span className="ml-1 font-sans text-[12px] font-normal text-muted">{unit}</span>}
              </span>
              <span className="text-[13px] text-muted">{s.label}</span>
            </span>
          );
        })}
      </div>

      <div
        ref={ref}
        className="relative mt-4 rounded-md outline-offset-4"
        role="group"
        aria-label={`${ariaLabel}. Use the left and right arrow keys to move between dates.`}
        tabIndex={0}
        onKeyDown={onKeyDown}
        onPointerLeave={() => setHover(null)}
        onBlur={() => setHover(null)}
      >
        {width > 0 && (
          <svg width={width} height={height} className="block overflow-visible" aria-hidden="true">
            {ticks.map((t) => (
              <g key={t}>
                <line x1={left} x2={width - M.right} y1={y(t)} y2={y(t)} className="stroke-line" strokeWidth={1} />
                <text x={left - 8} y={y(t) + 4} textAnchor="end" className="data fill-faint text-[11px]">
                  {formatNumber(t, Number.isInteger(t) ? 0 : 1)}
                </text>
              </g>
            ))}

            {/* Hovered date */}
            <rect
              x={left + band * active}
              y={M.top}
              width={band}
              height={plotBottom - M.top}
              className={`fill-mist transition-opacity duration-150 ${hover === null ? 'opacity-0' : 'opacity-60'}`}
            />

            {kind !== 'line' &&
              series.map((s, k) =>
                s.values.map((v, i) => {
                  let x: number;
                  let w: number;
                  if (kind === 'nested') {
                    w = k === 0 ? barW : barW * 0.42;
                    x = cx(i) - w / 2;
                  } else {
                    const gap = 2;
                    w = (barW - gap * (series.length - 1)) / series.length;
                    x = cx(i) - barW / 2 + k * (w + gap);
                  }
                  const top = y(v ?? 0);
                  return (
                    <motion.path
                      key={`${s.id}-${i}`}
                      initial={false}
                      animate={{ d: barPath(x, top, w, plotBottom - top) }}
                      transition={transition}
                      style={{ fill: s.color }}
                    />
                  );
                }),
              )}

            {kind === 'line' &&
              series.map((s) => {
                const points = s.values.flatMap((v, i) => (v === null ? [] : [{ x: cx(i), y: y(v), i }]));
                return (
                  <g key={s.id}>
                    <motion.path
                      initial={false}
                      animate={{ d: monotonePath(points) }}
                      transition={transition}
                      fill="none"
                      stroke={s.color}
                      strokeWidth={2}
                      strokeLinecap="round"
                    />
                    {points.map((p) => (
                      <motion.circle
                        key={p.i}
                        initial={false}
                        animate={{ cx: p.x, cy: p.y, r: p.i === active ? 5 : 3.5 }}
                        transition={transition}
                        fill={s.color}
                        className="stroke-surface"
                        strokeWidth={2}
                      />
                    ))}
                  </g>
                );
              })}

            <line x1={left} x2={width - M.right} y1={plotBottom} y2={plotBottom} className="stroke-line-strong" strokeWidth={1} />

            {labels.map((label, i) => (
              <text
                key={label}
                x={cx(i)}
                y={plotBottom + 17}
                textAnchor="middle"
                className={`data text-[11px] ${i === active ? 'fill-ink' : 'fill-faint'}`}
              >
                {i % labelEvery === 0 || i === active ? label : ''}
              </text>
            ))}

            {footer && (
              <>
                <text x={left - 8} y={HEIGHT + 10} textAnchor="end" className="fill-muted text-[11px]">
                  {footer.label}
                </text>
                {footer.values.map((value, i) => (
                  <text
                    key={i}
                    x={cx(i)}
                    y={HEIGHT + 10}
                    textAnchor="middle"
                    className={`data text-[11px] ${i === active ? 'fill-ink' : 'fill-muted'}`}
                  >
                    {i % labelEvery === 0 || i === active ? value : ''}
                  </text>
                ))}
              </>
            )}

            {/* Hit targets: the whole date band, not just the mark. */}
            {labels.map((label, i) => (
              <rect
                key={label}
                x={left + band * i}
                y={0}
                width={band}
                height={height}
                fill="transparent"
                onPointerEnter={() => setHover(i)}
                onPointerDown={() => setHover(i)}
              />
            ))}
          </svg>
        )}
        {width === 0 && <div style={{ height }} />}
      </div>
    </div>
  );
}
