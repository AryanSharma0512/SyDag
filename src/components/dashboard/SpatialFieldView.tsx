import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import type { SpatialContext, SpatialZone } from '../../types/agricultural';
import { AnimatedNumber } from '../common/AnimatedNumber';
import { DataBadge } from '../common/DataBadge';
import { SegmentedControl } from '../common/SegmentedControl';
import { EASE_OUT } from '../../utils/motion';
import { PALETTE as C, rampColor } from '../../utils/palette';
import type { Pt } from '../../utils/chart';

type Layer = 'satellite' | 'vegetation' | 'yield';

interface SpatialFieldViewProps {
  spatial: SpatialContext;
  fieldName: string;
}

/** Irregular field boundary (viewBox 600 × 400). Zones are warped to follow it. */
const CORNERS = { tl: { x: 46, y: 64 }, tr: { x: 548, y: 30 }, br: { x: 572, y: 350 }, bl: { x: 22, y: 374 } };

function bilerp(u: number, v: number): Pt {
  const top = { x: CORNERS.tl.x + (CORNERS.tr.x - CORNERS.tl.x) * u, y: CORNERS.tl.y + (CORNERS.tr.y - CORNERS.tl.y) * u };
  const bottom = { x: CORNERS.bl.x + (CORNERS.br.x - CORNERS.bl.x) * u, y: CORNERS.bl.y + (CORNERS.br.y - CORNERS.bl.y) * u };
  return { x: top.x + (bottom.x - top.x) * v, y: top.y + (bottom.y - top.y) * v };
}

const RAMPS = {
  satellite: ['#CDBEA5', '#A9A77F', '#7A9163', '#55744B'],
  vegetation: ['#EFE9D2', '#D5DEA2', '#9CC585', '#4B9C6C', '#17704B'],
  below: ['#ECE8DF', '#E3CDB6', '#C49A74'],
  above: ['#ECE8DF', '#A3CDB5', '#1B7F59'],
} as const;

const LAYERS: Array<{ value: Layer; label: string }> = [
  { value: 'satellite', label: 'Satellite' },
  { value: 'vegetation', label: 'Vegetation' },
  { value: 'yield', label: 'Yield' },
];

export function SpatialFieldView({ spatial, fieldName }: SpatialFieldViewProps) {
  const reduce = useReducedMotion();
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  const [layer, setLayer] = useState<Layer>('vegetation');
  const [selected, setSelected] = useState(13);
  const [hovering, setHovering] = useState(false);
  const [sweep, setSweep] = useState(false);
  const sweepTimer = useRef<number | undefined>(undefined);

  const zones = spatial.zones;
  const zone: SpatialZone | undefined = zones[Math.min(selected, zones.length - 1)];

  const geometry = useMemo(
    () =>
      zones.map((z) => {
        const u0 = z.gridCol / 4;
        const u1 = (z.gridCol + 1) / 4;
        const v0 = z.gridRow / 4;
        const v1 = (z.gridRow + 1) / 4;
        const pts = [bilerp(u0, v0), bilerp(u1, v0), bilerp(u1, v1), bilerp(u0, v1)];
        const center = bilerp((u0 + u1) / 2, (v0 + v1) / 2);
        return { points: pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '), center };
      }),
    [zones],
  );

  const meanYield = zones.reduce((sum, z) => sum + z.predictedYield, 0) / Math.max(1, zones.length);
  const maxDev = Math.max(4, ...zones.map((z) => Math.abs(z.predictedYield - meanYield)));

  const colorFor = (z: SpatialZone) => {
    if (layer === 'satellite') return rampColor(RAMPS.satellite, (z.ndvi - 0.3) / 0.62);
    if (layer === 'vegetation') return rampColor(RAMPS.vegetation, (z.ndvi - 0.3) / 0.62);
    const t = (z.predictedYield - meanYield) / maxDev;
    return t < 0 ? rampColor(RAMPS.below, -t) : rampColor(RAMPS.above, t);
  };

  const changeLayer = (next: Layer) => {
    setLayer(next);
    setSweep(true);
    window.clearTimeout(sweepTimer.current);
    sweepTimer.current = window.setTimeout(() => setSweep(false), 700);
  };

  useEffect(() => () => window.clearTimeout(sweepTimer.current), []);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const row = Math.floor(selected / 4);
    const col = selected % 4;
    let next = selected;
    if (event.key === 'ArrowRight') next = row * 4 + Math.min(3, col + 1);
    else if (event.key === 'ArrowLeft') next = row * 4 + Math.max(0, col - 1);
    else if (event.key === 'ArrowDown') next = Math.min(3, row + 1) * 4 + col;
    else if (event.key === 'ArrowUp') next = Math.max(0, row - 1) * 4 + col;
    else return;
    event.preventDefault();
    event.stopPropagation();
    setSelected(next);
  };

  const legend: { stops: readonly string[]; left: string; right: string; title: string } =
    layer === 'satellite'
      ? { stops: RAMPS.satellite, left: 'Bare soil', right: 'Dense canopy', title: 'Illustrative surface color' }
      : layer === 'vegetation'
        ? { stops: RAMPS.vegetation, left: '0.30', right: '0.92', title: 'NDVI' }
        : {
            stops: [...[...RAMPS.below].reverse(), ...RAMPS.above.slice(1)] as string[],
            left: `−${maxDev.toFixed(0)}`,
            right: `+${maxDev.toFixed(0)}`,
            title: `bu/ac vs field mean ${meanYield.toFixed(0)}`,
          };

  const zoneTransition = (z: SpatialZone) => ({
    duration: reduce ? 0 : sweep ? 0.3 : 0.38,
    delay: reduce ? 0 : sweep ? (z.gridRow + z.gridCol) * 0.03 : 0,
    ease: EASE_OUT,
  });

  return (
    <section className="rounded-2xl border border-line bg-surface transition-colors duration-300 hover:border-line-strong p-5 sm:p-6" aria-labelledby={`spatial-${uid}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 id={`spatial-${uid}`} className="text-[16px] font-semibold tracking-[-0.01em] text-ink">
              Spatial field view
            </h2>
            <DataBadge variant="illustrative" />
          </div>
          <p className="mt-1 text-[14px] text-muted">
            {fieldName} in 16 management zones. Hover or use arrow keys to inspect a zone.
          </p>
        </div>
        <SegmentedControl ariaLabel="Map layer" size="sm" value={layer} onChange={changeLayer} options={LAYERS} />
      </div>

      <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_260px] lg:gap-8">
        <div>
          <div
            tabIndex={0}
            role="group"
            aria-label="Field zones. Use the arrow keys to move between zones."
            onKeyDown={onKeyDown}
            className="relative overflow-hidden rounded-xl bg-canvas"
          >
            <svg viewBox="0 0 600 400" className="block h-auto w-full" aria-hidden="true">
              <defs>
                <pattern id={`rows-${uid}`} width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(-4)">
                  <line x1="0" y1="0" x2="9" y2="0" stroke="#FFFFFF" strokeWidth="1.3" />
                </pattern>
                <clipPath id={`field-${uid}`}>
                  <polygon points={geometry.length ? `${CORNERS.tl.x},${CORNERS.tl.y} ${CORNERS.tr.x},${CORNERS.tr.y} ${CORNERS.br.x},${CORNERS.br.y} ${CORNERS.bl.x},${CORNERS.bl.y}` : ''} />
                </clipPath>
                <filter id={`glow-${uid}`} x="-30%" y="-30%" width="160%" height="160%">
                  <feDropShadow dx="0" dy="3" stdDeviation="6" floodColor={C.ink} floodOpacity="0.28" />
                </filter>
              </defs>

              {/* Faint surrounding contours place the field in a landscape without competing with it. */}
              {[0, 1, 2, 3, 4].map((k) => (
                <path
                  key={k}
                  d={`M-20 ${40 + k * 86} C 140 ${20 + k * 86}, 320 ${70 + k * 86}, 620 ${34 + k * 86}`}
                  fill="none"
                  stroke={C.line}
                  strokeWidth={1}
                />
              ))}

              <g clipPath={`url(#field-${uid})`}>
                {zones.map((z, i) => (
                  <motion.polygon
                    key={z.id}
                    points={geometry[i].points}
                    stroke={C.surface}
                    strokeWidth={2.5}
                    strokeLinejoin="round"
                    initial={false}
                    animate={{ fill: colorFor(z) }}
                    transition={zoneTransition(z)}
                    onMouseEnter={() => {
                      setSelected(i);
                      setHovering(true);
                    }}
                    onMouseLeave={() => setHovering(false)}
                    onClick={() => setSelected(i)}
                    style={{ cursor: 'pointer' }}
                  />
                ))}
                <motion.rect
                  x={0}
                  y={0}
                  width={600}
                  height={400}
                  fill={`url(#rows-${uid})`}
                  pointerEvents="none"
                  initial={false}
                  animate={{ opacity: layer === 'satellite' ? 0.22 : 0 }}
                  transition={{ duration: reduce ? 0 : 0.45 }}
                />
              </g>

              <polygon
                points={`${CORNERS.tl.x},${CORNERS.tl.y} ${CORNERS.tr.x},${CORNERS.tr.y} ${CORNERS.br.x},${CORNERS.br.y} ${CORNERS.bl.x},${CORNERS.bl.y}`}
                fill="none"
                stroke={C.lineStrong}
                strokeWidth={1.5}
                strokeLinejoin="round"
              />

              {/* The selected zone lifts: a crisp copy with a soft shadow and a quiet outline. */}
              {zone && (
                <motion.g
                  key={zone.id}
                  pointerEvents="none"
                  style={{ originX: 0.5, originY: 0.5 }}
                  initial={reduce ? false : { scale: 1, opacity: 0 }}
                  animate={{ scale: 1.035, opacity: 1 }}
                  transition={{ duration: 0.22, ease: EASE_OUT }}
                >
                  <motion.polygon
                    points={geometry[selected].points}
                    stroke="#FFFFFF"
                    strokeWidth={3}
                    strokeLinejoin="round"
                    filter={`url(#glow-${uid})`}
                    initial={false}
                    animate={{ fill: colorFor(zone) }}
                    transition={zoneTransition(zone)}
                  />
                  <polygon
                    points={geometry[selected].points}
                    fill="none"
                    stroke={C.ink}
                    strokeOpacity={hovering ? 0.55 : 0.4}
                    strokeWidth={1.25}
                    strokeLinejoin="round"
                  />
                </motion.g>
              )}

              {zones.map((z, i) => (
                <text
                  key={`label-${z.id}`}
                  x={geometry[i].center.x}
                  y={geometry[i].center.y + 4}
                  textAnchor="middle"
                  pointerEvents="none"
                  className={`data text-[11px] transition-[fill] duration-300 ${
                    layer === 'satellite' ? 'fill-white/80' : i === selected ? 'fill-ink' : 'fill-ink/45'
                  }`}
                >
                  {i + 1}
                </text>
              ))}
            </svg>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <AnimatePresence initial={false} mode="wait">
              <motion.div
                key={layer}
                className="flex items-center gap-3"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
              >
                <span className="text-[12px] text-muted">{legend.title}</span>
                <span className="data text-[11px] text-faint">{legend.left}</span>
                <span
                  className="h-2 w-28 rounded-full"
                  style={{ background: `linear-gradient(90deg, ${legend.stops.join(', ')})` }}
                  aria-hidden="true"
                />
                <span className="data text-[11px] text-faint">{legend.right}</span>
              </motion.div>
            </AnimatePresence>
            <span className="text-[12px] text-muted">Values change with the selected date</span>
          </div>
        </div>

        {zone && (
          <div className="rounded-xl border border-line bg-canvas/60 p-4 sm:p-5" aria-live="polite">
            <div className="flex items-baseline justify-between">
              <span className="relative inline-grid overflow-hidden">
                <AnimatePresence initial={false} mode="popLayout">
                  <motion.span
                    key={zone.id}
                    className="text-[18px] font-semibold tracking-[-0.01em] text-ink"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.15 }}
                  >
                    {zone.name}
                  </motion.span>
                </AnimatePresence>
              </span>
              <span className="text-[12px] text-faint">Demo values</span>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-4 lg:grid-cols-1 lg:gap-y-0">
              {[
                { label: 'NDVI', value: <AnimatedNumber value={zone.ndvi} decimals={2} /> },
                {
                  label: 'Yield',
                  value: (
                    <>
                      <AnimatedNumber value={zone.predictedYield} decimals={0} />
                      <span className="ml-1 text-[12px] text-muted">bu/ac</span>
                    </>
                  ),
                },
                {
                  label: 'Rainfall',
                  value: (
                    <>
                      <AnimatedNumber value={zone.rainfall30Day} decimals={0} />
                      <span className="ml-1 text-[12px] text-muted">mm</span>
                    </>
                  ),
                },
                {
                  label: 'vs field mean',
                  value: (
                    <AnimatedNumber
                      value={zone.predictedYield - meanYield}
                      decimals={1}
                      format={(v) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`}
                    />
                  ),
                },
                { label: 'Soil', value: <span className="font-sans text-[14px] text-ink">{zone.soil}</span> },
              ].map((row) => (
                <div key={row.label} className="flex items-baseline justify-between gap-3 lg:border-t lg:border-line lg:py-3 lg:first:border-t-0 lg:first:pt-0">
                  <dt className="text-[13px] text-muted">{row.label}</dt>
                  <dd className="data text-[16px] font-medium text-ink">{row.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </div>
    </section>
  );
}
