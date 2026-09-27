import { useMemo, useState, type PointerEvent } from 'react';
import type { SitePerformance, ValidationMetrics } from '../../types/results';
import { nearestIndex, niceTicks, scaleLinear } from '../../utils/chart';
import { useElementWidth } from '../../utils/hooks';
import { PALETTE as C } from '../../utils/palette';

type Metric = 'r2' | 'mae' | 'medianIntervalWidth';

interface SiteTrajectoriesProps {
  sites: Array<{ id: string; name: string; performance: SitePerformance }>;
  metric: Metric;
  /** Shown under the grid, e.g. the validation scheme. */
  caption?: string;
}

const META: Record<Metric, { label: string; digits: number; unit: string; better: string }> = {
  r2: { label: 'R² (variation explained)', digits: 2, unit: '', better: 'higher is better' },
  mae: { label: 'Typical error (MAE)', digits: 1, unit: ' bu/ac', better: 'lower is better' },
  medianIntervalWidth: { label: 'Median 90% range width', digits: 0, unit: ' bu/ac', better: 'narrower is better' },
};

interface Point {
  key: string;
  label: string;
  dap: number;
  value: number;
  m: ValidationMetrics;
}

/**
 * One small panel per site on a shared scale, so sites compare at a glance without a
 * five-colour legend: the site's name labels its panel. The pre-season value (field
 * records only) sits at planting; a dashed segment joins it to the first satellite
 * stage, because nothing was observed in between.
 */
export function SiteTrajectories({ sites, metric, caption }: SiteTrajectoriesProps) {
  const meta = META[metric];
  const series = useMemo(
    () =>
      sites.map(({ id, name, performance }) => {
        const pre = performance.preseason?.[metric];
        const points: Point[] = [
          ...(pre != null && performance.preseason
            ? [{ key: 'pre', label: 'Before imagery', dap: 0, value: pre, m: performance.preseason }]
            : []),
          ...performance.stages
            .filter((s) => s[metric] != null)
            .map((s) => ({ key: s.stage, label: `${s.stage} · day ${s.dap}`, dap: s.dap, value: s[metric] as number, m: s })),
        ];
        return { id, name, plots: performance.plots, points };
      }),
    [sites, metric],
  );
  const all = series.flatMap((s) => s.points);
  if (!all.length) return null;

  const values = all.map((p) => p.value);
  const maxDap = Math.max(...all.map((p) => p.dap));
  let y0: number;
  let y1: number;
  if (metric === 'r2') {
    y0 = Math.min(0, Math.floor(Math.min(...values) * 10) / 10);
    y1 = Math.max(0.2, Math.ceil(Math.max(...values) * 10) / 10);
  } else {
    y0 = 0;
    y1 = Math.ceil(Math.max(...values) / 10) * 10;
  }

  return (
    <figure>
      <figcaption className="mb-3 text-[13px] text-muted">
        <span className="font-medium text-ink-soft">{meta.label}</span> · {meta.better} · days after planting on the x-axis
      </figcaption>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {series.map((s) => (
          <Panel key={s.id} name={s.name} plots={s.plots} points={s.points} domain={[y0, y1]} maxDap={maxDap} metric={metric} />
        ))}
      </div>
      {caption && <p className="mt-3 text-[12px] text-muted">{caption}</p>}
    </figure>
  );
}

function Panel({
  name,
  plots,
  points,
  domain,
  maxDap,
  metric,
}: {
  name: string;
  plots?: number | null;
  points: Point[];
  domain: [number, number];
  maxDap: number;
  metric: Metric;
}) {
  const meta = META[metric];
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const height = 170;
  const margin = { top: 22, right: 14, bottom: 24, left: 30 };
  const fmt = (v: number) => v.toFixed(meta.digits);

  const geo = useMemo(() => {
    if (width <= 0) return null;
    const sx = scaleLinear(0, maxDap, margin.left + 6, width - margin.right);
    const sy = scaleLinear(domain[0], domain[1], height - margin.bottom, margin.top);
    const pts = points.map((p) => ({ x: sx(p.dap), y: sy(p.value) }));
    const pre = points[0]?.key === 'pre' ? 1 : 0;
    const line = (from: number) =>
      pts
        .slice(from)
        .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
        .join('');
    return {
      sx,
      pts,
      solid: line(pre),
      dashed: pre && pts.length > 1 ? `M${pts[0].x},${pts[0].y}L${pts[1].x},${pts[1].y}` : null,
      ticks: niceTicks(domain[0], domain[1], 3).map((t) => ({ value: t, y: sy(t) })),
      days: [50, 100, 150].filter((d) => d <= maxDap + 5).map((d) => ({ d, x: sx(d) })),
      bottom: height - margin.bottom,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [width, points, domain, maxDap]);

  const onMove = (event: PointerEvent<SVGRectElement>) => {
    if (!geo) return;
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (rect)
      setHover(
        nearestIndex(
          geo.pts.map((p) => p.x),
          event.clientX - rect.left,
        ),
      );
  };

  const first = points[0];
  const last = points[points.length - 1];
  const tip = hover !== null && geo ? { p: points[hover], at: geo.pts[hover] } : null;

  return (
    <div className="rounded-xl border border-line bg-surface px-3 pt-3 pb-1">
      <div className="flex items-baseline justify-between gap-2 px-1">
        <h4 className="truncate text-[14px] font-semibold tracking-[-0.01em] text-ink">{name}</h4>
        {plots != null && <span className="data shrink-0 text-[11px] text-muted">{plots} plots</span>}
      </div>
      <div ref={ref} className="relative" style={{ height }}>
        {geo && (
          <svg
            width={width}
            height={height}
            className="overflow-visible"
            role="img"
            aria-label={`${name}, ${meta.label}: ${points.map((p) => `${p.label} ${fmt(p.value)}`).join('; ')}`}
          >
            {geo.ticks.map((t) => (
              <g key={t.value}>
                <line x1={margin.left} x2={width - margin.right} y1={t.y} y2={t.y} stroke={C.line} strokeWidth={1} />
                <text x={margin.left - 5} y={t.y + 3.5} textAnchor="end" className="data fill-faint text-[10px] tabular-nums">
                  {Number(t.value.toFixed(2))}
                </text>
              </g>
            ))}
            <line x1={margin.left} x2={width - margin.right} y1={geo.bottom} y2={geo.bottom} stroke={C.lineStrong} />
            {first?.key === 'pre' && (
              <text x={geo.pts[0].x} y={geo.bottom + 15} textAnchor="middle" className="fill-muted text-[10px]">
                Pre
              </text>
            )}
            {geo.days.map(({ d, x }) => (
              <text key={d} x={x} y={geo.bottom + 15} textAnchor="middle" className="data fill-faint text-[10px]">
                {d}
              </text>
            ))}

            {geo.dashed && (
              <path d={geo.dashed} fill="none" stroke={C.leaf400} strokeWidth={1.5} strokeDasharray="3 3" />
            )}
            <path d={geo.solid} fill="none" stroke={C.leaf700} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {geo.pts.map((pt, i) => (
              <circle
                key={points[i].key}
                cx={pt.x}
                cy={pt.y}
                r={4}
                fill={points[i].key === 'pre' ? C.surface : C.leaf700}
                stroke={points[i].key === 'pre' ? C.leaf700 : C.surface}
                strokeWidth={points[i].key === 'pre' ? 1.5 : 2}
              />
            ))}

            {/* Direct labels: where the site started and where it ended, never every point. */}
            {first && (
              <text
                x={geo.pts[0].x - 2}
                y={geo.pts[0].y - 9}
                textAnchor="start"
                stroke={C.surface}
                strokeWidth={4}
                paintOrder="stroke"
                className="data fill-ink-soft text-[11px] font-medium"
              >
                {fmt(first.value)}
              </text>
            )}
            {last && points.length > 1 && (
              <text
                x={geo.pts[geo.pts.length - 1].x + 2}
                y={geo.pts[geo.pts.length - 1].y - 9}
                textAnchor="end"
                stroke={C.surface}
                strokeWidth={4}
                paintOrder="stroke"
                className="data fill-ink text-[11px] font-semibold"
              >
                {fmt(last.value)}
              </text>
            )}

            <rect
              x={margin.left}
              y={0}
              width={Math.max(0, width - margin.left - margin.right + 8)}
              height={height}
              fill="transparent"
              onPointerMove={onMove}
              onPointerLeave={() => setHover(null)}
            />
            {tip && <circle cx={tip.at.x} cy={tip.at.y} r={7} fill="none" stroke={C.leaf700} strokeWidth={1.5} pointerEvents="none" />}
          </svg>
        )}
        {tip && (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-10 w-[180px] rounded-xl border border-line bg-surface/95 px-3 py-2.5 text-[12px] shadow-lift backdrop-blur-sm"
            style={{ left: Math.min(Math.max(0, tip.at.x - 90), Math.max(0, width - 180)), top: Math.max(0, tip.at.y - 104) }}
          >
            <div className="font-medium text-ink">{tip.p.label}</div>
            <dl className="mt-1.5 space-y-0.5 border-t border-line pt-1.5">
              {(
                [
                  ['R²', tip.p.m.r2, (v: number) => v.toFixed(2)],
                  ['MAE', tip.p.m.mae, (v: number) => `${v.toFixed(1)} bu/ac`],
                  ['Range width', tip.p.m.medianIntervalWidth, (v: number) => `${v.toFixed(0)} bu/ac`],
                  ['Inside range', tip.p.m.coverage, (v: number) => `${Math.round(v * 100)}%`],
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
          </div>
        )}
      </div>
    </div>
  );
}
