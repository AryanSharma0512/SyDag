/**
 * Small, dependency-free chart geometry helpers used by the hand-built SVG
 * charts. Paths keep a stable command structure for a given point count, which
 * lets Motion interpolate the `d` attribute smoothly when data changes.
 */

export interface Pt {
  x: number;
  y: number;
}

export type Scale = (value: number) => number;

export function scaleLinear(d0: number, d1: number, r0: number, r1: number): Scale {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (value: number) => r0 + (value - d0) * k;
}

/** Parses an ISO calendar date at noon UTC so time zones never shift the day. */
export function toTime(iso: string): number {
  return Date.parse(`${iso}T12:00:00Z`);
}

const round = (v: number) => Math.round(v * 100) / 100;

/**
 * Monotone cubic interpolation (the same tangent rule as d3's curveMonotoneX):
 * smooth, and never overshoots the data between points.
 */
export function monotonePath(points: Pt[]): string {
  const n = points.length;
  if (n === 0) return '';
  const start = `M${round(points[0].x)},${round(points[0].y)}`;
  if (n === 1) return start;
  if (n === 2) return `${start}L${round(points[1].x)},${round(points[1].y)}`;

  const tangents = new Array<number>(n).fill(0);
  for (let i = 1; i < n - 1; i++) {
    const h0 = points[i].x - points[i - 1].x;
    const h1 = points[i + 1].x - points[i].x;
    const s0 = (points[i].y - points[i - 1].y) / h0;
    const s1 = (points[i + 1].y - points[i].y) / h1;
    const p = (s0 * h1 + s1 * h0) / (h0 + h1);
    tangents[i] = (Math.sign(s0) + Math.sign(s1)) * Math.min(Math.abs(s0), Math.abs(s1), 0.5 * Math.abs(p)) || 0;
  }
  const hStart = points[1].x - points[0].x;
  tangents[0] = hStart ? ((3 * (points[1].y - points[0].y)) / hStart - tangents[1]) / 2 : tangents[1];
  const hEnd = points[n - 1].x - points[n - 2].x;
  tangents[n - 1] = hEnd ? ((3 * (points[n - 1].y - points[n - 2].y)) / hEnd - tangents[n - 2]) / 2 : tangents[n - 2];

  let d = start;
  for (let i = 0; i < n - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    const dx = (b.x - a.x) / 3;
    d += `C${round(a.x + dx)},${round(a.y + dx * tangents[i])},${round(b.x - dx)},${round(b.y - dx * tangents[i + 1])},${round(b.x)},${round(b.y)}`;
  }
  return d;
}

/** Closed area between an upper and a lower curve (both ordered left to right). */
export function bandPath(upper: Pt[], lower: Pt[]): string {
  if (upper.length === 0) return '';
  const top = monotonePath(upper);
  const bottom = monotonePath([...lower].reverse());
  return `${top}L${bottom.slice(1)}Z`;
}

/** Evenly spaced "nice" tick values covering [min, max]. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  const span = max - min;
  if (span <= 0) return [min];
  const raw = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const ticks: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) ticks.push(Math.round(v * 1000) / 1000);
  return ticks;
}

/** Index of the value closest to the target. */
export function nearestIndex(values: number[], target: number): number {
  let best = 0;
  let bestDistance = Infinity;
  values.forEach((value, index) => {
    const distance = Math.abs(value - target);
    if (distance < bestDistance) {
      best = index;
      bestDistance = distance;
    }
  });
  return best;
}
