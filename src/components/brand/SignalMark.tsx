/**
 * The SoilSignal mark, drawn on a 32-unit grid.
 *
 * A seedling rises from two soil horizons; its tip is a sensor node that
 * broadcasts two signal arcs. Growth, ground and signal in one glyph.
 */

export const BRAND_COLORS = {
  leaf: '#17684B',
  signal: '#97C5A9',
  soil: '#A2653A',
  soilLight: '#D4B2A0',
  ink: '#14202B',
} as const;

/** The sensor node at the tip of the stem; both signal arcs share it as their center. */
export const NODE = { x: 20.21, y: 10.01, r: 1.54 } as const;

export const STROKES = { soil: 2.6, stem: 1.9, arc: 1.9 } as const;

const r2 = (v: number) => Math.round(v * 100) / 100;

/** Quarter arc around the node, sweeping clockwise from straight up to straight right. */
export function signalArc(radius: number): string {
  const { x, y } = NODE;
  return `M${x} ${r2(y - radius)}A${radius} ${radius} 0 0 1 ${r2(x + radius)} ${y}`;
}

export const MARK_PATHS = {
  horizonTop: 'M6.7 25.66H26.84',
  horizonLow: 'M3.61 30.16H19.02',
  leaf: 'M5.99 9.78C11.2 9.01 15.05 12.27 16.06 16.53L15.64 18.07C10.61 18.67 6.46 15.23 5.99 9.78Z',
  stem: 'M16.18 24.12C16.06 17.01 17.13 13.45 20.21 10.01',
  /** Inner arc: the node's first signal ring. */
  arc: signalArc(4.74),
  /** Outer echo: the signal radiating outward. */
  echo: signalArc(8.53),
} as const;

/** The mark's shapes, unanimated, for embedding inside another 32-unit SVG group. */
export function MarkShapes() {
  return (
    <g fill="none">
      <path d={MARK_PATHS.horizonTop} stroke={BRAND_COLORS.soil} strokeWidth={STROKES.soil} strokeLinecap="round" />
      <path d={MARK_PATHS.horizonLow} stroke={BRAND_COLORS.soilLight} strokeWidth={STROKES.soil} strokeLinecap="round" />
      <path d={MARK_PATHS.leaf} fill={BRAND_COLORS.leaf} />
      <path d={MARK_PATHS.stem} stroke={BRAND_COLORS.leaf} strokeWidth={STROKES.stem} strokeLinecap="round" />
      <circle cx={NODE.x} cy={NODE.y} r={NODE.r} fill={BRAND_COLORS.leaf} />
      <path d={MARK_PATHS.arc} stroke={BRAND_COLORS.leaf} strokeWidth={STROKES.arc} strokeLinecap="round" />
      <path d={MARK_PATHS.echo} stroke={BRAND_COLORS.signal} strokeWidth={STROKES.arc} strokeLinecap="round" />
    </g>
  );
}

interface SignalMarkProps {
  size?: number;
  className?: string;
  title?: string;
}

export function SignalMark({ size = 28, className, title }: SignalMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={className}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <MarkShapes />
    </svg>
  );
}
