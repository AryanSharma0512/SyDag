/**
 * Ambient paths for the hero's sensing layer. Everything here is a pure function
 * of time, so the scene can be drawn at any instant: the ambient loop samples it
 * every frame, and t = 0 is the resting frame shown with reduced motion.
 *
 * The drone works a survey plan in plot coordinates (column, row on the field's
 * top face): it glides to a plot and hovers to inspect it, sweeps slowly along a
 * row, orbits a plot, then repositions. Each plan returns to its home plot so
 * the loop is seamless.
 *
 * The satellite travels a shallow arc across the sky, highest over its imaging
 * node, fading in at the left edge and out before the forecast card; after a
 * pause off-frame it re-enters from the left.
 */

/** A point on the field's top face in plot units: column and row, fractional between plots. */
export type PlotPt = readonly [col: number, row: number];

export type Leg =
  | { kind: 'hold'; dur: number }
  | { kind: 'fly'; to: PlotPt; dur: number; bow: number; sweep: boolean }
  | { kind: 'orbit'; around: PlotPt; dur: number; dir: 1 | -1 };

export interface FlightPlan {
  home: PlotPt;
  /** The legs flown from home, in order. The last must end back at home. */
  legs: Leg[];
}

/** Hover over the current plot. */
export const hold = (dur: number): Leg => ({ kind: 'hold', dur });
/** Transit to a plot, easing in and out; `bow` bends the path sideways (a fraction of its length). */
export const fly = (to: PlotPt, dur: number, bow = 0): Leg => ({ kind: 'fly', to, dur, bow, sweep: false });
/** A slow, steady scan along a row: quick to reach cruise speed, then constant. */
export const sweep = (to: PlotPt, dur: number): Leg => ({ kind: 'fly', to, dur, bow: 0, sweep: true });
/** One full circle around a plot, starting and ending at the current position. */
export const orbit = (around: PlotPt, dur: number, dir: 1 | -1 = 1): Leg => ({ kind: 'orbit', around, dur, dir });

interface TimedLeg {
  leg: Leg;
  start: number;
  from: PlotPt;
}

export interface Flight {
  legs: TimedLeg[];
  period: number;
}

export function compileFlight(plan: FlightPlan): Flight {
  let start = 0;
  let at = plan.home;
  const legs = plan.legs.map((leg) => {
    const timed = { leg, start, from: at };
    start += leg.dur;
    if (leg.kind === 'fly') at = leg.to;
    return timed;
  });
  return { legs, period: start };
}

const easeInOutCubic = (k: number) => (k < 0.5 ? 4 * k ** 3 : 1 - (-2 * k + 2) ** 3 / 2);
const easeInOutSine = (k: number) => (1 - Math.cos(Math.PI * k)) / 2;

/** Accelerate over the first `a` of the leg, cruise, then decelerate over the last `a`. */
function cruise(k: number, a: number) {
  const v = 1 / (1 - a);
  if (k < a) return (v * k * k) / (2 * a);
  if (k > 1 - a) return 1 - (v * (1 - k) ** 2) / (2 * a);
  return v * (k - a / 2);
}

/** Where the drone's scan footprint is, in plot units, t seconds into the loop. */
export function flightAt(flight: Flight, t: number): PlotPt {
  const time = ((t % flight.period) + flight.period) % flight.period;
  const timed = flight.legs.find((l) => time < l.start + l.leg.dur) ?? flight.legs[flight.legs.length - 1];
  const { leg, from } = timed;
  const k = Math.min(1, Math.max(0, (time - timed.start) / leg.dur));
  const [c0, r0] = from;
  if (leg.kind === 'hold') return from;
  if (leg.kind === 'orbit') {
    const a = leg.dir * 2 * Math.PI * easeInOutSine(k);
    const [cc, rc] = leg.around;
    const dc = c0 - cc;
    const dr = r0 - rc;
    return [cc + dc * Math.cos(a) - dr * Math.sin(a), rc + dc * Math.sin(a) + dr * Math.cos(a)];
  }
  const s = leg.sweep ? cruise(k, 0.28) : easeInOutCubic(k);
  const dc = leg.to[0] - c0;
  const dr = leg.to[1] - r0;
  const bulge = leg.bow * 4 * s * (1 - s);
  return [c0 + dc * s - dr * bulge, r0 + dr * s + dc * bulge];
}

export function smoothstep(e0: number, e1: number, x: number) {
  const h = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)));
  return h * h * (3 - 2 * h);
}

export interface SatTrack {
  /** Altitude of the arc's apex, which sits over `park`. */
  y: number;
  /** Where the intro pass parks the satellite (over its imaging node); the ambient loop starts here. */
  park: number;
  /** The loop's left and right ends, where the satellite is fully faded. */
  enter: number;
  exit: number;
  fadeIn: number;
  fadeOut: number;
  /** How far below the apex the arc starts at the left edge. */
  arc: number;
  /** Cruise speed (viewBox units per second) and the pause off-frame between passes. */
  speed: number;
  gap: number;
}

/** Satellite position and visibility t seconds after it leaves its parked position. */
export function satelliteAt(track: SatTrack, t: number) {
  // Ease out of the parked position instead of starting at full speed.
  const tau = 2.5;
  const travelled = track.speed * (t - tau * (1 - Math.exp(-t / tau)));
  const span = track.exit - track.enter;
  const loop = span + track.gap * track.speed;
  const q = (((track.park - track.enter + travelled) % loop) + loop) % loop;
  const x = track.enter + Math.min(q, span);
  const opacity =
    q > span ? 0 : smoothstep(track.enter, track.enter + track.fadeIn, x) * (1 - smoothstep(track.exit - track.fadeOut, track.exit, x));
  const rel = (x - track.park) / (track.park - track.enter);
  return { x, y: track.y + track.arc * rel * rel, opacity };
}
