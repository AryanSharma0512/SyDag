/**
 * The SoilSignal mark, drawn on a 32-unit grid.
 *
 * Read top to bottom it is one abstract S: a signal arc sweeps left, a crop
 * leaf carries the curve back across, and two soil horizons close it out.
 * Signal, growth and ground in a single gesture.
 */

export const BRAND_COLORS = {
  leaf: '#086C4C',
  soil: '#A66A3F',
  ink: '#14202B',
} as const;

/** Shared center of the signal arcs. */
export const ARC_CENTER = { x: 16.2, y: 11.9 } as const;

const toRad = (deg: number) => (deg * Math.PI) / 180;
const r2 = (v: number) => Math.round(v * 100) / 100;

/** Counter-clockwise arc around the mark's signal center, from angle a0 to a1 (degrees, SVG space). */
export function signalArc(radius: number, a0: number, a1: number): string {
  const { x, y } = ARC_CENTER;
  const sx = r2(x + radius * Math.cos(toRad(a0)));
  const sy = r2(y + radius * Math.sin(toRad(a0)));
  const ex = r2(x + radius * Math.cos(toRad(a1)));
  const ey = r2(y + radius * Math.sin(toRad(a1)));
  return `M${sx} ${sy}A${radius} ${radius} 0 0 0 ${ex} ${ey}`;
}

export const MARK_PATHS = {
  /** Inner arc: the top bowl of the S. */
  arc: signalArc(7, -28, -172),
  /** Outer echo: the signal radiating outward. */
  echo: signalArc(10.8, -24, -62),
  leaf: 'M9.6 14C14.4 12.7 21.8 15.1 23.4 20.4C18.6 21.7 11.2 19.3 9.6 14Z',
  horizonTop: 'M10.5 24.6H26',
  horizonLow: 'M6 29.1H19',
} as const;

interface SignalMarkProps {
  size?: number;
  /** `compact` drops the outer echo and thickens strokes for favicon-sized use. */
  variant?: 'full' | 'compact';
  className?: string;
  title?: string;
}

export function SignalMark({ size = 28, variant = 'full', className, title }: SignalMarkProps) {
  const compact = variant === 'compact';
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
      <path d={MARK_PATHS.horizonTop} stroke={BRAND_COLORS.soil} strokeWidth={compact ? 3 : 2.6} strokeLinecap="round" />
      <path
        d={MARK_PATHS.horizonLow}
        stroke={BRAND_COLORS.soil}
        strokeWidth={compact ? 3 : 2.6}
        strokeLinecap="round"
        opacity={0.5}
      />
      <path d={MARK_PATHS.leaf} fill={BRAND_COLORS.leaf} />
      <path
        d={MARK_PATHS.arc}
        stroke={BRAND_COLORS.leaf}
        strokeWidth={compact ? 3.2 : 2.7}
        strokeLinecap="round"
      />
      {!compact && (
        <path d={MARK_PATHS.echo} stroke={BRAND_COLORS.leaf} strokeWidth={2.3} strokeLinecap="round" opacity={0.45} />
      )}
    </svg>
  );
}
