import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react';
import { useMediaQuery } from '../../utils/hooks';
import { bandPath, monotonePath, scaleLinear, type Pt } from '../../utils/chart';
import { EASE_OUT } from '../../utils/motion';
import { PALETTE as C } from '../../utils/palette';
import { MarkShapes } from '../brand/SignalMark';
import { compileFlight, fly, flightAt, hold, orbit, satelliteAt, smoothstep, sweep, type FlightPlan, type SatTrack } from './heroFlight';

/**
 * The SoilSignal story in one scene, played once (~5s desktop, ~3.6s mobile):
 *   1. seeds and roots appear in a soil cross-section
 *   2. maize emerges and sets tassels and ears
 *   3. fine rain traces pass through, and a drone flies in over the canopy
 *   4. a satellite pass sweeps the field and lights up field zones
 *   5. satellite, drone, weather and field-record nodes activate and feed SoilSignal
 *   6. the signal resolves into a yield forecast curve and value
 * Afterwards the sensing layer keeps working (see heroFlight.ts): the drone
 * surveys the plots, lighting the one it inspects, and the satellite drifts on,
 * fades out before the forecast card and returns on a slow loop, washing the
 * field as it crosses and downlinking as it passes its node. Data dots travel
 * into SoilSignal and on to the forecast, nodes pulse, leaves shift and the
 * contours drift. With reduced motion the scene rests on its final frame.
 */

interface NodeSpec {
  x: number;
  y: number;
  label: string;
  color: string;
  labelSide: 'left' | 'right';
}

interface SceneConfig {
  w: number;
  h: number;
  block: { x0: number; x1: number; frontY: number; backY: number; skew: number; bottom: number };
  horizons: [number, number];
  frontRow: number;
  backRow: number;
  plantHeight: [number, number];
  rain: number;
  /** The intro pass runs from `from` to `track.park`; the ambient loop continues along `track`. */
  satellite: {
    from: number;
    track: SatTrack;
    /** Distance from the imaging node over which the downlink fades in (near) and out (far). */
    link: [number, number];
    /** Distance from the satellite at which its swath fully lights (near) and stops lighting (far) a plot. */
    swath: [number, number];
  };
  drone: {
    scale: number;
    /** Height above the plot being scanned, and the extra height it climbs to while transiting. */
    alt: number;
    climb: number;
    /** Half-width of the scan cone where it meets the plots. */
    footprint: number;
    flight: FlightPlan;
  };
  nodes: { spectral: NodeSpec; weather: NodeSpec; soil: NodeSpec };
  /** Vertical offset at which each source line meets the hub, ordered so the lines never cross. */
  arrivals: Record<'spectral' | 'weather' | 'drone' | 'soil', number>;
  hub: { x: number; y: number; r: number };
  card: { x: number; y: number; w: number; h: number };
  cells: [number, number];
  labels: boolean;
  /** Timing multiplier; mobile plays a shorter sequence. */
  time: number;
  stroke: number;
}

const DESKTOP: SceneConfig = {
  w: 1200,
  h: 520,
  block: { x0: 36, x1: 660, frontY: 346, backY: 300, skew: 46, bottom: 500 },
  horizons: [394, 448],
  frontRow: 11,
  backRow: 10,
  plantHeight: [70, 100],
  rain: 26,
  satellite: {
    from: -90,
    track: { y: 50, park: 716, enter: -40, exit: 890, fadeIn: 150, fadeOut: 110, arc: 16, speed: 22, gap: 6 },
    link: [50, 150],
    swath: [12, 46],
  },
  drone: {
    scale: 1.45,
    alt: 170,
    climb: 8,
    footprint: 34,
    // Plots are 12 columns by 3 rows; the survey keeps to columns 5-9 so the drone
    // stays clear of the weather and satellite nodes.
    flight: {
      home: [7, 1],
      legs: [
        hold(2.4),
        fly([5, 0], 3, 0.25),
        hold(1.8),
        sweep([8, 0], 6),
        hold(1.2),
        orbit([8, 1], 7.5, -1),
        fly([9, 2], 2.6, -0.3),
        hold(2.2),
        sweep([6, 2], 5.6),
        hold(1.4),
        fly([5, 1], 2.2, 0.3),
        hold(2),
        fly([7, 1], 3, -0.25),
      ],
    },
  },
  nodes: {
    spectral: { x: 716, y: 138, label: 'Satellite', color: C.leaf500, labelSide: 'left' },
    weather: { x: 236, y: 188, label: 'Weather', color: C.rain500, labelSide: 'left' },
    soil: { x: 478, y: 466, label: 'Field records', color: C.soil500, labelSide: 'left' },
  },
  arrivals: { spectral: -9, drone: -3, weather: 3, soil: 9 },
  hub: { x: 848, y: 232, r: 25 },
  card: { x: 902, y: 88, w: 270, h: 222 },
  cells: [12, 3],
  labels: true,
  time: 1,
  stroke: 1,
};

const MOBILE: SceneConfig = {
  w: 720,
  h: 600,
  block: { x0: 16, x1: 404, frontY: 410, backY: 370, skew: 40, bottom: 584 },
  horizons: [458, 516],
  frontRow: 6,
  backRow: 0,
  plantHeight: [112, 142],
  rain: 10,
  satellite: {
    from: -80,
    track: { y: 44, park: 430, enter: -50, exit: 545, fadeIn: 110, fadeOut: 80, arc: 12, speed: 16, gap: 5 },
    link: [36, 110],
    swath: [14, 50],
  },
  drone: {
    scale: 1.7,
    alt: 212,
    climb: 8,
    footprint: 40,
    // A simpler survey on phones: columns 1-3 of 7, no orbit.
    flight: {
      home: [1, 1],
      legs: [hold(2.4), fly([2, 0], 3, 0.25), hold(1.8), sweep([3, 0], 3.6), hold(1.6), fly([3, 1], 2.2), hold(1.8), sweep([1, 1], 6)],
    },
  },
  nodes: {
    spectral: { x: 430, y: 136, label: 'Satellite', color: C.leaf500, labelSide: 'left' },
    weather: { x: 262, y: 92, label: 'Weather', color: C.rain500, labelSide: 'left' },
    soil: { x: 236, y: 530, label: 'Field records', color: C.soil500, labelSide: 'left' },
  },
  arrivals: { spectral: -9, weather: -3, drone: 3, soil: 9 },
  hub: { x: 504, y: 300, r: 30 },
  card: { x: 552, y: 150, w: 162, h: 262 },
  cells: [7, 2],
  labels: false,
  time: 0.72,
  stroke: 1.6,
};

/** Deterministic pseudo-random numbers so the scene is identical on every load. */
function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

/** Minimal cubic-bezier easing, used to time the satellite scan against the zones it passes. */
function bezierEase(x1: number, y1: number, x2: number, y2: number) {
  const coord = (t: number, a: number, b: number) => 3 * a * t * (1 - t) ** 2 + 3 * b * t ** 2 * (1 - t) + t ** 3;
  return (x: number) => {
    let lo = 0;
    let hi = 1;
    for (let i = 0; i < 24; i++) {
      const mid = (lo + hi) / 2;
      if (coord(mid, x1, x2) < x) lo = mid;
      else hi = mid;
    }
    return coord((lo + hi) / 2, y1, y2);
  };
}

const SAT_EASE = [0.45, 0, 0.55, 1] as const;
const satEase = bezierEase(...SAT_EASE);
/** Inverse of the satellite easing: at what fraction of the pass does it reach progress p? */
function satTimeAt(p: number) {
  let lo = 0;
  let hi = 1;
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2;
    if (satEase(mid) < p) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}

const round = (v: number) => Math.round(v * 10) / 10;

/**
 * A maize plant: a gently leaning stem with alternating arching blades, a tassel
 * at the top and one ear on the stalk. Each blade has a midrib stroke (drawn in)
 * and a filled outline (faded in once the midrib is down).
 */
function plantGeometry(x: number, base: number, height: number, seed: number, width: number) {
  const lean = Math.sin(seed * 2.3) * 3;
  const stem = `M${round(x)},${round(base)} C${round(x + lean * 0.2)},${round(base - height * 0.45)} ${round(x + lean * 0.8)},${round(base - height * 0.75)} ${round(x + lean)},${round(base - height)}`;
  const leaves: Array<{ rib: string; blade: string }> = [];
  for (let k = 0; k < 4; k++) {
    const t = 0.26 + k * 0.18;
    const ay = base - height * t;
    const ax = x + lean * t;
    const dir = (k + seed) % 2 === 0 ? 1 : -1;
    const len = height * (0.5 - k * 0.075);
    const rise = len * 0.42;
    const c1 = { x: ax + dir * len * 0.3, y: ay - rise };
    const c2 = { x: ax + dir * len * 0.72, y: ay - rise * 0.95 };
    const tip = { x: ax + dir * len, y: ay - rise * 0.35 };
    // The blade widens above the midrib and tapers to the same tip.
    const w = width * (1 - k * 0.12);
    leaves.push({
      rib: `M${round(ax)},${round(ay)} C${round(c1.x)},${round(c1.y)} ${round(c2.x)},${round(c2.y)} ${round(tip.x)},${round(tip.y)}`,
      blade: `M${round(ax)},${round(ay)} C${round(c1.x)},${round(c1.y - w)} ${round(c2.x)},${round(c2.y - w * 0.9)} ${round(tip.x)},${round(tip.y)} C${round(c2.x)},${round(c2.y + w * 0.2)} ${round(c1.x)},${round(c1.y + w * 0.3)} ${round(ax)},${round(ay)}Z`,
    });
  }
  const top = { x: x + lean, y: base - height };
  // The ear sits on the side of the lowest blade, just above it, leaning outward.
  const earT = 0.4;
  const ear = { x: x + lean * earT, y: base - height * earT, dir: seed % 2 === 0 ? 1 : -1, len: height * 0.24 };
  return { stem, leaves, top, ear };
}

/** Tassel branches spreading from the top of the stem (drawn relative to the stem tip). */
function tasselGeometry(size: number) {
  const s = size;
  return [
    `M0,0 C0,${-s * 0.4} ${s * 0.05},${-s * 0.75} 0,${-s}`,
    `M0,${-s * 0.2} C${-s * 0.2},${-s * 0.5} ${-s * 0.45},${-s * 0.62} ${-s * 0.62},${-s * 0.48}`,
    `M0,${-s * 0.2} C${s * 0.2},${-s * 0.52} ${s * 0.46},${-s * 0.66} ${s * 0.64},${-s * 0.5}`,
    `M0,${-s * 0.42} C${-s * 0.12},${-s * 0.7} ${-s * 0.28},${-s * 0.84} ${-s * 0.38},${-s * 0.8}`,
    `M0,${-s * 0.42} C${s * 0.14},${-s * 0.72} ${s * 0.3},${-s * 0.86} ${s * 0.4},${-s * 0.82}`,
  ];
}

/** An ear of maize drawn upward from its attachment point: cob, kernel rows, husk and silk. */
function EarShape({ len, sw }: { len: number; sw: number }) {
  const w = len * 0.36;
  return (
    <>
      <ellipse cx={0} cy={-len * 0.56} rx={w * 0.5} ry={len * 0.42} fill={C.sun300} stroke={C.sun500} strokeWidth={0.7 * sw} />
      <path
        d={`M${-w * 0.16},${-len * 0.24} C${-w * 0.22},${-len * 0.5} ${-w * 0.2},${-len * 0.74} ${-w * 0.08},${-len * 0.92}M${w * 0.16},${-len * 0.24} C${w * 0.22},${-len * 0.5} ${w * 0.2},${-len * 0.74} ${w * 0.08},${-len * 0.92}`}
        fill="none"
        stroke={C.sun500}
        strokeWidth={0.55 * sw}
        opacity={0.55}
      />
      <path
        d={`M0,0 C${-w * 0.95},${-len * 0.2} ${-w * 0.8},${-len * 0.62} ${-w * 0.12},${-len * 0.82} C${-w * 0.3},${-len * 0.52} ${-w * 0.22},${-len * 0.22} 0,0Z`}
        fill={C.leaf500}
      />
      <path
        d={`M0,0 C${w * 0.9},${-len * 0.18} ${w * 0.78},${-len * 0.5} ${w * 0.2},${-len * 0.66} C${w * 0.34},${-len * 0.42} ${w * 0.22},${-len * 0.18} 0,0Z`}
        fill={C.leaf600}
      />
      <path
        d={`M0,${-len * 0.96} c${-w * 0.2},${-len * 0.12} ${-w * 0.5},${-len * 0.14} ${-w * 0.7},${-len * 0.08}M0,${-len * 0.96} c${w * 0.1},${-len * 0.14} ${w * 0.4},${-len * 0.2} ${w * 0.62},${-len * 0.16}`}
        fill="none"
        stroke={C.soil400}
        strokeWidth={0.8 * sw}
        strokeLinecap="round"
      />
    </>
  );
}

/** Side view of a quadcopter, centered on its body. Rotors blur when the scene is live. */
function DroneShape({ spin }: { spin: boolean }) {
  return (
    <>
      <path d="M-24 -4H24" stroke={C.inkSoft} strokeWidth={2} strokeLinecap="round" />
      {[-24, 24].map((x) => (
        <g key={x}>
          <rect x={x - 1.6} y={-8.5} width={3.2} height={5} rx={1} fill={C.inkSoft} />
          <ellipse cx={x} cy={-9.5} rx={11} ry={2.4} fill={C.ink} opacity={0.08} />
          <path
            d={`M${x - 10} -9.5H${x + 10}`}
            stroke={C.inkSoft}
            strokeWidth={1.4}
            strokeLinecap="round"
            className={spin ? 'ss-rotor' : undefined}
            style={spin ? { animationDelay: x < 0 ? '0s' : '-0.07s' } : undefined}
          />
        </g>
      ))}
      <rect x={-10} y={-7} width={20} height={9} rx={4.2} fill={C.inkSoft} />
      <rect x={-6} y={-5.2} width={7} height={2.4} rx={1.2} fill={C.rain300} opacity={0.9} />
      <circle cx={6} cy={-3} r={1.3} fill={C.leaf300} />
      <path d="M-7 2L-10 8M7 2L10 8M-12 8H-8M8 8H12" stroke={C.inkSoft} strokeWidth={1.2} strokeLinecap="round" />
      <circle cx={0} cy={4.8} r={3.1} fill={C.ink} />
      <circle cx={0} cy={5.4} r={1.2} fill={C.leaf300} />
    </>
  );
}

function rootGeometry(x: number, y: number, depth: number) {
  return [
    `M${x},${y} C${x - 3},${y + depth * 0.35} ${x + 4},${y + depth * 0.65} ${x + 1},${y + depth}`,
    `M${x - 1},${y + depth * 0.22} C${x - 8},${y + depth * 0.3} ${x - 14},${y + depth * 0.42} ${x - 18},${y + depth * 0.6}`,
    `M${x + 1},${y + depth * 0.36} C${x + 8},${y + depth * 0.42} ${x + 13},${y + depth * 0.56} ${x + 16},${y + depth * 0.76}`,
    `M${x},${y + depth * 0.56} C${x - 5},${y + depth * 0.64} ${x - 8},${y + depth * 0.75} ${x - 10},${y + depth * 0.9}`,
  ];
}

/** Gentle horizontal S-curve between two points, used for converging signal lines. */
function flowCurve(from: Pt, to: Pt): [Pt, Pt, Pt, Pt] {
  const dx = to.x - from.x;
  return [from, { x: from.x + dx * 0.55, y: from.y }, { x: to.x - dx * 0.45, y: to.y }, to];
}

function curvePath([a, b, c, d]: [Pt, Pt, Pt, Pt]) {
  return `M${round(a.x)},${round(a.y)} C${round(b.x)},${round(b.y)} ${round(c.x)},${round(c.y)} ${round(d.x)},${round(d.y)}`;
}

const flowPath = (from: Pt, to: Pt) => curvePath(flowCurve(from, to));

function cubicAt([a, b, c, d]: [Pt, Pt, Pt, Pt], t: number): Pt {
  const m = 1 - t;
  const w = [m * m * m, 3 * m * m * t, 3 * m * t * t, t * t * t];
  return { x: w[0] * a.x + w[1] * b.x + w[2] * c.x + w[3] * d.x, y: w[0] * a.y + w[1] * b.y + w[2] * c.y + w[3] * d.y };
}

/** Piecewise-linear keyframes, [time, value] pairs with times ascending over 0..1. */
function keyframe(stops: Array<[number, number]>, k: number) {
  for (let i = 1; i < stops.length; i++) {
    const [t1, v1] = stops[i];
    if (k <= t1) {
      const [t0, v0] = stops[i - 1];
      return v0 + ((v1 - v0) * (k - t0)) / (t1 - t0);
    }
  }
  return stops[stops.length - 1][1];
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/**
 * The drone in screen space at time t of its survey: the ground point it scans,
 * its own position above that point, and its bank, climb and depth scale, all
 * derived from the flight path so they stay in step.
 */
function makeSurvey(cfg: SceneConfig, onTop: (u: number, v: number) => Pt) {
  const { drone } = cfg;
  const [cols, rows] = cfg.cells;
  const flight = compileFlight(drone.flight);
  const ground = (t: number) => {
    const [c, r] = flightAt(flight, t);
    const v = (r + 0.5) / rows;
    return { ...onTop((c + 0.5) / cols, v), c, r, v };
  };
  const step = 1 / 30;
  return (t: number) => {
    const g = ground(t);
    const prev = ground(t - step);
    const vx = (g.x - prev.x) / step;
    const speed = Math.hypot(vx, (g.y - prev.y) / step);
    // A little higher while transiting, settling back down to inspect.
    const alt = drone.alt + drone.climb * smoothstep(0, 90, speed);
    return {
      gx: g.x,
      gy: g.y,
      x: g.x,
      y: g.y - alt,
      // Nearer plots are lower on screen, so the drone is drawn slightly larger over them.
      scale: drone.scale * (1 + 0.1 * (0.5 - g.v)),
      // Banks into its direction of travel, as a multirotor does.
      tilt: clamp(vx * 0.09, -8, 8),
      footprint: (drone.footprint * alt) / drone.alt,
      cell: clamp(Math.round(g.r), 0, rows - 1) * cols + clamp(Math.round(g.c), 0, cols - 1),
    };
  };
}

type DroneState = ReturnType<ReturnType<typeof makeSurvey>>;

const droneBodyTransform = (d: DroneState) => `rotate(${d.tilt.toFixed(2)}) scale(${d.scale.toFixed(3)})`;

/** Scan footprint: a disc lying on the field's top face, sheared to match its perspective. */
function footprintTransform(d: DroneState, cfg: SceneConfig) {
  const r = d.footprint;
  const depth = r * 0.3;
  const shear = (depth * cfg.block.skew) / (cfg.block.frontY - cfg.block.backY);
  return `matrix(${round(r)} 0 ${round(-shear)} ${round(depth)} ${round(d.gx)} ${round(d.gy)})`;
}

/** The drone's scan cone, from its camera down to the plot under it. */
function beamPoints(d: DroneState) {
  const top = d.y + 9 * d.scale;
  const w = 5 * d.scale;
  return `${round(d.x - w)},${round(top)} ${round(d.x + w)},${round(top)} ${round(d.gx + d.footprint)},${round(d.gy)} ${round(d.gx - d.footprint)},${round(d.gy)}`;
}

/** Illustrative season shape (normalized time) echoing the default demo field. */
const SEASON = {
  t: [0, 0.17, 0.32, 0.48, 0.56, 0.64, 0.82, 1],
  mid: [152, 161.4, 169.8, 179.2, 184.3, 184.0, 186.2, 185.1],
  lo: [131, 143.2, 154.5, 166.4, 171.2, 173.5, 178, 179.5],
  hi: [173, 179.6, 185.1, 192, 196.7, 194.5, 194.4, 190.7],
};

function buildScene(cfg: SceneConfig) {
  const { x0, x1, frontY, backY, skew, bottom } = cfg.block;
  const depth = frontY - backY;
  const onTop = (u: number, v: number): Pt => ({ x: x0 + u * (x1 - x0) + v * skew, y: frontY - v * depth });
  const rand = seeded(cfg.w + cfg.frontRow);

  const plants: Array<{ x: number; base: number; height: number; row: 'front' | 'back'; seed: number; rootX: number }> = [];
  const [hMin, hMax] = cfg.plantHeight;
  for (let i = 0; i < cfg.frontRow; i++) {
    const u = 0.07 + (i / Math.max(1, cfg.frontRow - 1)) * 0.86;
    const p = onTop(u, 0.24);
    const height = hMin + (hMax - hMin) * (0.5 + 0.5 * Math.sin(i * 1.7 + 0.4));
    plants.push({ x: p.x, base: p.y, height, row: 'front', seed: i, rootX: p.x - 0.24 * skew });
  }
  for (let i = 0; i < cfg.backRow; i++) {
    const u = 0.11 + (i / Math.max(1, cfg.backRow - 1)) * 0.8;
    const p = onTop(u, 0.68);
    const height = (hMin + (hMax - hMin) * (0.5 + 0.5 * Math.sin(i * 2.1 + 1.3))) * 0.84;
    plants.push({ x: p.x, base: p.y, height, row: 'back', seed: i + 1, rootX: p.x });
  }

  // Cells are stored row by row, so the plot at (column i, row j) is cells[j * cols + i].
  const [cols, rows] = cfg.cells;
  const cells = [];
  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < cols; i++) {
      const gu = 0.006;
      const gv = 0.05;
      const a = onTop(i / cols + gu, j / rows + gv);
      const b = onTop((i + 1) / cols - gu, j / rows + gv);
      const c = onTop((i + 1) / cols - gu, (j + 1) / rows - gv);
      const d = onTop(i / cols + gu, (j + 1) / rows - gv);
      const vigor = 0.5 + 0.5 * Math.sin(i * 0.9 + j * 1.7 + 0.6) * Math.cos(i * 0.37);
      cells.push({
        key: `${i}-${j}`,
        points: [a, b, c, d].map((p) => `${round(p.x)},${round(p.y)}`).join(' '),
        cx: (a.x + c.x) / 2,
        finalOpacity: 0.12 + vigor * 0.3,
      });
    }
  }

  const rain = Array.from({ length: cfg.rain }, (_, i) => ({
    key: i,
    x: x0 + skew * 0.5 + rand() * (x1 - x0),
    y: 96 + rand() * 60,
    len: (12 + rand() * 9) * cfg.stroke,
    fall: backY - 150 - rand() * 40,
    delay: rand() * 0.55,
    dur: 0.7 + rand() * 0.2,
  }));

  const wave = (y: number, amp: number, phase: number) => {
    const pts: Pt[] = [];
    for (let x = x0; x <= x1 + 0.1; x += (x1 - x0) / 12) pts.push({ x, y: y + amp * Math.sin(x / 47 + phase) });
    return monotonePath(pts);
  };

  const dots = Array.from({ length: Math.round((x1 - x0) / 26) }, (_, i) => ({
    key: i,
    x: x0 + 14 + rand() * (x1 - x0 - 28),
    y: cfg.horizons[0] + 10 + rand() * (bottom - cfg.horizons[0] - 18),
    r: 1 + rand() * 0.9,
  }));

  const contours = Array.from({ length: 7 }, (_, k) => {
    const pts: Pt[] = [];
    const y = 30 + k * 38;
    for (let x = -60; x <= cfg.w + 80; x += 90) {
      pts.push({ x, y: y + 9 * Math.sin(x / 170 + k * 0.9) + 5 * Math.sin(x / 67 + k * 2.1) });
    }
    return monotonePath(pts);
  });

  const { hub, card, nodes, satellite, arrivals } = cfg;
  const droneAt = makeSurvey(cfg, onTop);
  const home = droneAt(0);
  const arrive = (dy: number): Pt => ({ x: hub.x - hub.r - 1, y: hub.y + dy });
  const droneLink = (d: DroneState) => flowCurve({ x: d.x + 4 * d.scale, y: d.y + 3 * d.scale }, arrive(arrivals.drone));
  const lines = [
    { key: 'spectral', color: nodes.spectral.color, d: flowPath(nodes.spectral, arrive(arrivals.spectral)) },
    { key: 'weather', color: nodes.weather.color, d: flowPath(nodes.weather, arrive(arrivals.weather)) },
    { key: 'drone', color: C.sun500, d: curvePath(droneLink(home)) },
    { key: 'soil', color: nodes.soil.color, d: flowPath(nodes.soil, arrive(arrivals.soil)) },
  ];
  // The satellite beams down to its imagery node while it is overhead.
  const downlinkFrom = (sat: Pt): [Pt, Pt] => [
    { x: sat.x, y: sat.y + 14 * cfg.stroke },
    { x: nodes.spectral.x, y: nodes.spectral.y - 8 * cfg.stroke },
  ];
  const [linkA, linkB] = downlinkFrom({ x: satellite.track.park, y: satellite.track.y });
  const downlink = `M${round(linkA.x)},${round(linkA.y)}L${round(linkB.x)},${round(linkB.y)}`;

  const pad = cfg.labels ? 20 : 14;
  const chart = {
    left: card.x + pad,
    right: card.x + card.w - pad,
    top: card.y + (cfg.labels ? 84 : 104),
    bottom: card.y + card.h - (cfg.labels ? 34 : 22),
  };
  const sx = scaleLinear(0, 1, chart.left, chart.right);
  const sy = scaleLinear(125, 205, chart.bottom, chart.top);
  const mid = SEASON.t.map((t, i) => ({ x: sx(t), y: sy(SEASON.mid[i]) }));
  const hi = SEASON.t.map((t, i) => ({ x: sx(t), y: sy(SEASON.hi[i]) }));
  const lo = SEASON.t.map((t, i) => ({ x: sx(t), y: sy(SEASON.lo[i]) }));
  const last = SEASON.t.length - 1;
  const forecast = {
    chart,
    line: monotonePath(mid),
    band: bandPath(hi, lo),
    bandCollapsed: bandPath(mid, mid),
    end: mid[mid.length - 1],
    value: Math.round(SEASON.mid[last]),
    range: Math.round((SEASON.hi[last] - SEASON.lo[last]) / 2),
    connector: flowPath({ x: hub.x + hub.r + 1, y: hub.y }, mid[0]),
    grid: [150, 175, 200].map((v) => sy(v)),
    months: [
      { label: 'Jun', x: sx(0.08) },
      { label: 'Jul', x: sx(0.4) },
      { label: 'Aug', x: sx(0.7) },
      { label: 'Sep', x: sx(0.96) },
    ],
  };

  return {
    droneAt,
    home,
    droneLink,
    downlinkFrom,
    plants,
    cells,
    rain,
    dots,
    contours,
    lines,
    downlink,
    forecast,
    faces: {
      top: [onTop(0, 0), onTop(1, 0), onTop(1, 1), onTop(0, 1)].map((p) => `${round(p.x)},${round(p.y)}`).join(' '),
      side: `${x1},${frontY} ${x1 + skew},${backY} ${x1 + skew},${bottom - depth} ${x1},${bottom}`,
      horizonA: wave(cfg.horizons[0], 2.6, 0.4),
      horizonB: wave(cfg.horizons[1], 3.2, 2.1),
    },
  };
}

type LiveKey =
  | 'drone'
  | 'droneBody'
  | 'beam'
  | 'scan'
  | 'footprint'
  | 'droneLine'
  | 'droneDot'
  | 'sat'
  | 'swath'
  | 'link'
  | 'linkPath'
  | 'linkDot';

/** How strongly the plot under the drone is lit while it inspects it. */
const PLOT_LIT = 0.85;
const SCAN_PERIOD = 2.6;
const SCAN_FADE: Array<[number, number]> = [
  [0, 0],
  [0.12, 0.75],
  [0.8, 0.5],
  [1, 0],
];
const DOT_FADE: Array<[number, number]> = [
  [0, 0],
  [0.12, 1],
  [0.84, 1],
  [1, 0],
];

/** A data dot with a soft halo; the ambient loop positions it. */
function DataDot({ ref, color, sw }: { ref: (el: SVGElement | null) => void; color: string; sw: number }) {
  return (
    <g ref={ref} opacity={0}>
      <circle r={6 * sw} fill={color} opacity={0.18} />
      <circle r={2.6 * sw} fill={color} />
    </g>
  );
}

export function HeroSystemAnimation() {
  const isMobile = useMediaQuery('(max-width: 767px)');
  const reduce = useReducedMotion();
  // The composition is chosen once so a resize never restarts the story.
  const [cfg] = useState(() => (isMobile ? MOBILE : DESKTOP));
  const scene = useMemo(() => buildScene(cfg), [cfg]);
  const [settled, setSettled] = useState(false);

  const T = (s: number) => s * cfg.time;
  const D = (s: number) => s * (cfg.time < 1 ? 0.85 : 1);
  const END = 5.1;

  useEffect(() => {
    if (reduce) {
      setSettled(true);
      return;
    }
    const id = window.setTimeout(() => setSettled(true), T(END) * 1000);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduce]);

  // Motion's hook reads the preference once; this one follows it live, so switching reduced
  // motion on mid-visit also stops the ambient layer and returns the scene to its resting frame.
  const reduceNow = useMediaQuery('(prefers-reduced-motion: reduce)');
  const ambient = settled && !reduce && !reduceNow;

  // Elements the ambient loop moves directly, outside React's render path.
  const rootRef = useRef<HTMLDivElement>(null);
  const live = useRef<Partial<Record<LiveKey, SVGElement>>>({});
  const bind = (key: LiveKey) => (el: SVGElement | null) => {
    if (el) live.current[key] = el;
    else delete live.current[key];
  };
  const plotRefs = useRef<Array<SVGPolygonElement | null>>([]);
  const washRefs = useRef<Array<SVGPolygonElement | null>>([]);

  // One clock drives the drone's survey, the satellite's loop, the plots they light and
  // the data leaving each of them. It pauses while the hero is off screen.
  useEffect(() => {
    if (!ambient) return;
    const el = live.current;
    const { cells, droneAt, droneLink, downlinkFrom, home } = scene;
    const { track, link, swath } = cfg.satellite;
    const { block } = cfg;
    const n = cells.length;
    const plots = new Float32Array(n);
    const wash = new Float32Array(n);
    // What is currently in the DOM, so unchanged plots are not rewritten every frame.
    const shownPlots = new Float32Array(n);
    const shownWash = new Float32Array(n);
    plots[home.cell] = 1;
    shownPlots[home.cell] = PLOT_LIT;
    let flash = 0;
    let lastScan = 0;
    const fieldL = block.x0 + block.skew * 0.5;
    const fieldR = block.x1 + block.skew * 0.5;
    const overField = (x: number) => smoothstep(fieldL - 30, fieldL + 10, x) * (1 - smoothstep(fieldR - 10, fieldR + 30, x));
    const sw = cfg.stroke;
    const write = (node: SVGElement | null | undefined, shown: Float32Array, i: number, value: number) => {
      if (Math.abs(value - shown[i]) < 0.004) return;
      shown[i] = value;
      node?.setAttribute('opacity', value.toFixed(3));
    };

    const draw = (t: number, dt: number) => {
      // Drone: position, bank, cone and footprint.
      const d = droneAt(t);
      el.drone?.setAttribute('transform', `translate(${round(d.x)} ${round(d.y)})`);
      el.droneBody?.setAttribute('transform', droneBodyTransform(d));
      el.beam?.setAttribute('points', beamPoints(d));
      el.footprint?.setAttribute('transform', footprintTransform(d, cfg));

      // A scan line runs down the cone; as it lands, the footprint and its plot flash.
      const scan = (t % SCAN_PERIOD) / SCAN_PERIOD;
      if (scan < lastScan) flash = 1;
      lastScan = scan;
      flash *= Math.exp(-dt * 3);
      const e = scan ** 1.6;
      const top = d.y + 9 * d.scale;
      const y = round(top + (d.gy - top) * e);
      const half = 5 * d.scale + (d.footprint - 5 * d.scale) * e;
      el.scan?.setAttribute('x1', `${round(d.x - half)}`);
      el.scan?.setAttribute('x2', `${round(d.x + half)}`);
      el.scan?.setAttribute('y1', `${y}`);
      el.scan?.setAttribute('y2', `${y}`);
      el.scan?.setAttribute('opacity', keyframe(SCAN_FADE, scan).toFixed(3));
      el.footprint?.setAttribute('opacity', (0.8 + 0.2 * flash).toFixed(3));

      // Its data rides the line to SoilSignal, which bends as the drone moves.
      const curve = droneLink(d);
      el.droneLine?.setAttribute('d', curvePath(curve));
      // Same period and in-out curve (keySplines 0.45 0 0.55 1) as the other lines' SMIL dots.
      const k = (t % 3.2) / 3.2;
      const dot = cubicAt(curve, satEase(k));
      el.droneDot?.setAttribute('transform', `translate(${round(dot.x)} ${round(dot.y)})`);
      el.droneDot?.setAttribute('opacity', keyframe(DOT_FADE, k).toFixed(3));

      // Satellite: loops across the sky, imaging the field as it crosses.
      const sat = satelliteAt(track, t);
      const imaging = sat.opacity * overField(sat.x);
      el.sat?.setAttribute('transform', `translate(${round(sat.x - track.park)} ${round(sat.y - track.y)})`);
      el.sat?.setAttribute('opacity', sat.opacity.toFixed(3));
      const swathTop = sat.y + 12 * sw;
      el.swath?.setAttribute(
        'points',
        `${round(sat.x - 4 * sw)},${round(swathTop)} ${round(sat.x + 4 * sw)},${round(swathTop)} ${round(sat.x + 24 * sw)},${block.backY + 18} ${round(sat.x - 24 * sw)},${block.backY + 18}`,
      );
      el.swath?.setAttribute('opacity', (0.45 * imaging).toFixed(3));

      // ...and downlinks while it is over its node.
      const contact = sat.opacity * (1 - smoothstep(link[0], link[1], Math.abs(sat.x - cfg.nodes.spectral.x)));
      const [a, b] = downlinkFrom(sat);
      el.linkPath?.setAttribute('d', `M${round(a.x)},${round(a.y)}L${round(b.x)},${round(b.y)}`);
      el.link?.setAttribute('opacity', contact.toFixed(3));
      const q = (t % 1.8) / 1.8;
      const eq = satEase(q);
      el.linkDot?.setAttribute('transform', `translate(${round(a.x + (b.x - a.x) * eq)} ${round(a.y + (b.y - a.y) * eq)})`);
      el.linkDot?.setAttribute('opacity', keyframe(DOT_FADE, q).toFixed(3));

      // Plots: the one under the drone brightens while it lingers and fades once it moves on;
      // the satellite's swath washes whole columns and leaves a slower wake.
      const trail = Math.exp(-dt / 1.6);
      const rise = 1 - Math.exp(-dt * 2.2);
      const wake = Math.exp(-dt / 1.4);
      for (let i = 0; i < n; i++) {
        plots[i] = i === d.cell ? plots[i] + (1 - plots[i]) * rise : plots[i] * trail;
        const near = 1 - smoothstep(swath[0], swath[1], Math.abs(cells[i].cx - sat.x));
        wash[i] = Math.max(near * imaging, wash[i] * wake);
        write(plotRefs.current[i], shownPlots, i, plots[i] * PLOT_LIT + (i === d.cell ? 0.15 * flash : 0));
        write(washRefs.current[i], shownWash, i, wash[i] * 0.55);
      }
    };

    let raf = 0;
    let running = false;
    let last = 0;
    let t = 0;
    const frame = (now: number) => {
      // Clamp the step so a stalled or backgrounded tab resumes smoothly instead of jumping.
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 0;
      last = now;
      t += dt;
      draw(t, dt);
      raf = requestAnimationFrame(frame);
    };
    const start = () => {
      if (running) return;
      running = true;
      last = 0;
      raf = requestAnimationFrame(frame);
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(raf);
    };
    const observer = new IntersectionObserver(([entry]) => (entry.isIntersecting ? start() : stop()));
    if (rootRef.current) observer.observe(rootRef.current);
    else start();

    return () => {
      stop();
      observer.disconnect();
      // Back to the resting frame (reduced motion was switched on, or the hero is unmounting).
      plots.fill(0);
      plots[home.cell] = 1;
      wash.fill(0);
      flash = 0;
      lastScan = 0;
      draw(0, 0);
    };
  }, [ambient, cfg, scene]);

  // Scroll: the field system gently compresses as the product section takes over.
  const { scrollY } = useScroll();
  const scaleY = useTransform(scrollY, [0, 620], [1, 0.9]);
  const scaleX = useTransform(scrollY, [0, 620], [1, 0.97]);
  const opacity = useTransform(scrollY, [0, 520], [1, 0.4]);
  const lift = useTransform(scrollY, [0, 620], [0, -24]);

  const { block, satellite, nodes, hub, card, drone } = cfg;
  const { track } = satellite;
  const { forecast, home } = scene;
  const sw = cfg.stroke;
  const satDelay = T(2.35);
  const satDur = D(1.15);

  const nodeList = [nodes.spectral, nodes.weather, nodes.soil];
  // The fixed paths the ambient data dots loop along: sources into the hub, the hub out to the
  // forecast. The drone's line and the satellite downlink move, so the ambient loop carries theirs.
  const flows = [
    ...scene.lines.map((line, i) => ({ key: line.key, d: line.d, color: line.color, dur: 3.2, begin: 0.4 + i * 0.8 })),
    { key: 'forecast', d: forecast.connector, color: C.leaf700, dur: 1.6, begin: 0.2 },
  ].filter((flow) => flow.key !== 'drone');

  return (
    <motion.div
      ref={rootRef}
      className="relative w-full select-none"
      style={{
        aspectRatio: `${cfg.w} / ${cfg.h}`,
        ...(reduce ? {} : { scaleX, scaleY, opacity, y: lift, originY: 1 }),
      }}
      role="img"
      aria-label="Illustration: a maize plot is planted and grows ears, rain passes, a drone surveys the plots and a satellite images the field as it passes overhead. Satellite and drone imagery, weather and the field record feed SoilSignal, which produces a yield forecast."
    >
      {/* Background topographic contours, on their own layer so drifting stays on the compositor. */}
      <motion.svg
        viewBox={`0 0 ${cfg.w} ${cfg.h}`}
        className={`absolute inset-0 h-full w-full ${ambient ? 'ss-drift' : ''}`}
        aria-hidden="true"
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.2, ease: 'easeOut' }}
      >
        {scene.contours.map((d, k) => (
          <path key={k} d={d} fill="none" stroke={C.lineStrong} strokeWidth={1} opacity={0.55 - k * 0.04} />
        ))}
      </motion.svg>

      <svg viewBox={`0 0 ${cfg.w} ${cfg.h}`} className="absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
        <defs>
          <linearGradient id="hero-beam" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.leaf300} stopOpacity="0" />
            <stop offset="100%" stopColor={C.leaf300} stopOpacity="0.5" />
          </linearGradient>
          <linearGradient id="hero-drone-beam" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.leaf300} stopOpacity="0.5" />
            <stop offset="100%" stopColor={C.leaf300} stopOpacity="0.16" />
          </linearGradient>
          <radialGradient id="hero-footprint">
            <stop offset="0%" stopColor={C.leaf300} stopOpacity="0.8" />
            <stop offset="65%" stopColor={C.leaf300} stopOpacity="0.45" />
            <stop offset="100%" stopColor={C.leaf300} stopOpacity="0" />
          </radialGradient>
          <linearGradient id="hero-band" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={C.leaf400} stopOpacity="0.1" />
            <stop offset="100%" stopColor={C.leaf400} stopOpacity="0.22" />
          </linearGradient>
          <filter id="hero-card-shadow" x="-20%" y="-20%" width="140%" height="150%">
            <feDropShadow dx="0" dy="8" stdDeviation="12" floodColor={C.ink} floodOpacity="0.09" />
          </filter>
        </defs>

        {/* ---- Soil block ------------------------------------------------ */}
        <motion.g
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: D(0.5), ease: 'easeOut' }}
        >
          <polygon points={scene.faces.side} fill="#EFE5D8" />
          <polygon points={scene.faces.top} fill="#F5EFE6" />
          <rect x={block.x0} y={block.frontY} width={block.x1 - block.x0} height={cfg.horizons[0] - block.frontY} fill={C.soil100} />
          <rect x={block.x0} y={cfg.horizons[0]} width={block.x1 - block.x0} height={cfg.horizons[1] - cfg.horizons[0]} fill="#F6EEE5" />
          <rect x={block.x0} y={cfg.horizons[1]} width={block.x1 - block.x0} height={block.bottom - cfg.horizons[1]} fill="#F9F4EE" />
          {scene.dots.map((dot) => (
            <circle key={dot.key} cx={dot.x} cy={dot.y} r={dot.r * sw} fill={C.soil300} opacity={0.55} />
          ))}
        </motion.g>

        {/* Top-face field zones: they light up as the satellite passes, then settle into a faint vigor map. */}
        {scene.cells.map((cell) => {
          const progress = (cell.cx - satellite.from) / (track.park - satellite.from);
          const at = satDelay + satDur * satTimeAt(Math.min(1, Math.max(0, progress)));
          return (
            <motion.polygon
              key={cell.key}
              points={cell.points}
              fill={C.leaf300}
              initial={reduce ? false : { opacity: 0 }}
              animate={reduce ? { opacity: cell.finalOpacity } : { opacity: [0, 0.95, cell.finalOpacity] }}
              transition={{ delay: at - 0.05, duration: D(0.9), times: [0, 0.18, 1], ease: 'easeOut' }}
            />
          );
        })}

        {/* Survey marks on the plots, beneath the crop: the satellite's swath washes the columns it
            crosses, and the drone's footprint lights the plot it is inspecting, leaving a fading trail. */}
        <motion.g
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: T(2.8), duration: D(0.5), ease: 'easeOut' }}
        >
          {scene.cells.map((cell, k) => (
            <polygon
              key={`wash-${cell.key}`}
              ref={(node) => {
                washRefs.current[k] = node;
              }}
              points={cell.points}
              fill={C.leaf300}
              opacity={0}
            />
          ))}
          {scene.cells.map((cell, k) => (
            <polygon
              key={`plot-${cell.key}`}
              ref={(node) => {
                plotRefs.current[k] = node;
              }}
              points={cell.points}
              fill={C.leaf400}
              fillOpacity={0.3}
              stroke={C.leaf500}
              strokeWidth={1.2 * sw}
              strokeLinejoin="round"
              opacity={k === home.cell ? PLOT_LIT : 0}
            />
          ))}
          <ellipse
            ref={bind('footprint')}
            rx={1}
            ry={1}
            transform={footprintTransform(home, cfg)}
            fill="url(#hero-footprint)"
            opacity={0.8}
          />
        </motion.g>

        {/* Horizon lines draw left to right. */}
        {[
          { d: `M${block.x0},${block.frontY}H${block.x1}`, color: C.soil400, width: 1.3, delay: 0.1 },
          { d: scene.faces.horizonA, color: C.soil300, width: 1, delay: 0.24 },
          { d: scene.faces.horizonB, color: C.soil300, width: 1, delay: 0.38 },
        ].map((line) => (
          <motion.path
            key={line.d}
            d={line.d}
            fill="none"
            stroke={line.color}
            strokeWidth={line.width * sw}
            strokeLinecap="round"
            initial={reduce ? false : { pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ pathLength: { delay: T(line.delay), duration: D(0.8), ease: EASE_OUT }, opacity: { delay: T(line.delay), duration: 0.1 } }}
          />
        ))}
        <path
          d={`M${block.x1},${block.frontY}L${block.x1 + block.skew},${block.backY}`}
          stroke={C.soil300}
          strokeWidth={sw}
          opacity={0.8}
        />

        {/* ---- Phase 1: seeds and roots --------------------------------- */}
        {scene.plants
          .filter((p) => p.row === 'front')
          .map((p, i) => (
            <g key={`root-${i}`}>
              <motion.ellipse
                cx={p.rootX}
                cy={block.frontY + 5}
                rx={3.4 * sw}
                ry={2.3 * sw}
                fill={C.soil500}
                initial={reduce ? false : { scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 0.9 }}
                transition={{ delay: T(0.45 + i * 0.03), duration: D(0.3), ease: EASE_OUT }}
              />
              {rootGeometry(p.rootX, block.frontY + 7, (cfg.horizons[0] - block.frontY) * 1.45).map((d, k) => (
                <motion.path
                  key={k}
                  d={d}
                  fill="none"
                  stroke={C.soil600}
                  strokeWidth={(k === 0 ? 1.2 : 0.9) * sw}
                  strokeLinecap="round"
                  initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity: 0.5 }}
                  transition={{
                    pathLength: { delay: T(0.6 + i * 0.03 + k * 0.08), duration: D(0.75), ease: EASE_OUT },
                    opacity: { delay: T(0.6 + i * 0.03 + k * 0.08), duration: 0.1 },
                  }}
                />
              ))}
            </g>
          ))}

        {/* ---- Phase 2: maize emerges (back row first, lighter) ---------- */}
        {[...scene.plants]
          .sort((a, b) => (a.row === b.row ? 0 : a.row === 'back' ? -1 : 1))
          .map((p, i) => {
            const back = p.row === 'back';
            const geo = plantGeometry(p.x, p.base, p.height, p.seed, (back ? 2.2 : 4) * sw);
            const delay = T(1.05 + (back ? 0 : 0.12) + (p.x / cfg.w) * 0.55);
            const swayIndex = i % 3 === 0;
            return (
              <motion.g
                key={`plant-${p.row}-${p.seed}`}
                style={{ originX: 0.5, originY: 1 }}
                initial={reduce ? false : { scale: 0.3, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay, duration: D(0.8), ease: EASE_OUT }}
              >
                <g
                  className={ambient && swayIndex ? 'ss-sway' : undefined}
                  style={ambient && swayIndex ? { animationDelay: `${(i * 1.7) % 9}s`, animationDuration: `${10 + (i % 4)}s` } : undefined}
                >
                  <path
                    d={geo.stem}
                    fill="none"
                    stroke={back ? C.leaf300 : C.leaf700}
                    strokeWidth={(back ? 1.8 : 2.6) * sw}
                    strokeLinecap="round"
                  />
                  {geo.leaves.map((leaf, k) => {
                    const leafDelay = delay + T(0.18 + k * 0.08);
                    return (
                      <g key={k}>
                        {!back && (
                          <motion.path
                            d={leaf.blade}
                            fill={k > 1 ? C.leaf400 : C.leaf500}
                            initial={reduce ? false : { opacity: 0 }}
                            animate={{ opacity: 0.92 }}
                            transition={{ delay: leafDelay + D(0.3), duration: D(0.4), ease: 'easeOut' }}
                          />
                        )}
                        <motion.path
                          d={leaf.rib}
                          fill="none"
                          stroke={back ? C.leaf200 : k > 1 ? C.leaf600 : C.leaf700}
                          strokeWidth={(back ? 1.7 : 1.9) * sw}
                          strokeLinecap="round"
                          initial={reduce ? false : { pathLength: 0 }}
                          animate={{ pathLength: 1 }}
                          transition={{ delay: leafDelay, duration: D(0.5), ease: EASE_OUT }}
                        />
                      </g>
                    );
                  })}
                  {!back && (
                    <>
                      <g transform={`translate(${round(geo.ear.x)} ${round(geo.ear.y)}) rotate(${geo.ear.dir * 24})`}>
                        <motion.g
                          style={{ originX: 0.5, originY: 1 }}
                          initial={reduce ? false : { scale: 0, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ delay: delay + T(0.62), duration: D(0.5), ease: EASE_OUT }}
                        >
                          <EarShape len={geo.ear.len} sw={sw} />
                        </motion.g>
                      </g>
                      <g transform={`translate(${round(geo.top.x)} ${round(geo.top.y)})`}>
                        <motion.g
                          style={{ originX: 0.5, originY: 1 }}
                          initial={reduce ? false : { scale: 0, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ delay: delay + T(0.52), duration: D(0.45), ease: EASE_OUT }}
                        >
                          {tasselGeometry(p.height * 0.15).map((d, k) => (
                            <path
                              key={k}
                              d={d}
                              fill="none"
                              stroke={k === 0 ? C.sun500 : C.sun300}
                              strokeWidth={(k === 0 ? 1.4 : 1.1) * sw}
                              strokeLinecap="round"
                            />
                          ))}
                        </motion.g>
                      </g>
                    </>
                  )}
                </g>
              </motion.g>
            );
          })}

        {/* ---- Phase 3: rain traces --------------------------------------- */}
        {!reduce &&
          scene.rain.map((drop) => (
            <motion.line
              key={drop.key}
              x1={drop.x}
              x2={drop.x}
              y1={drop.y}
              y2={drop.y + drop.len}
              stroke={C.rain500}
              strokeWidth={sw}
              strokeLinecap="round"
              initial={{ y: -30, opacity: 0 }}
              animate={{ y: drop.fall, opacity: [0, 0.7, 0.7, 0] }}
              transition={{
                delay: T(1.75 + drop.delay),
                duration: D(drop.dur),
                ease: 'easeIn',
                opacity: { delay: T(1.75 + drop.delay), duration: D(drop.dur), times: [0, 0.15, 0.75, 1] },
              }}
            />
          ))}

        {/* The satellite's imaging swath on later passes, under the drone so it never tints it. */}
        {ambient && <polygon ref={bind('swath')} fill="url(#hero-beam)" opacity={0} />}

        {/* ---- Drone: flies in over the canopy, then surveys the plots ------- */}
        <motion.g
          initial={reduce ? false : { x: -home.x - 60 * drone.scale, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ x: { delay: T(1.55), duration: D(1.4), ease: EASE_OUT }, opacity: { delay: T(1.55), duration: 0.3 } }}
        >
          <motion.g
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: T(2.8), duration: D(0.5), ease: 'easeOut' }}
          >
            <polygon ref={bind('beam')} points={beamPoints(home)} fill="url(#hero-drone-beam)" />
            {ambient && <line ref={bind('scan')} stroke={C.leaf400} strokeWidth={1.6 * sw} strokeLinecap="round" opacity={0} />}
          </motion.g>
          <g ref={bind('drone')} transform={`translate(${round(home.x)} ${round(home.y)})`}>
            <g className={ambient ? 'ss-hover' : undefined}>
              <g ref={bind('droneBody')} transform={droneBodyTransform(home)}>
                <DroneShape spin={!reduce} />
              </g>
            </g>
            {cfg.labels && (
              <motion.text
                x={-38 * drone.scale}
                y={0}
                textAnchor="end"
                className="fill-muted text-[12px] font-medium"
                initial={reduce ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: T(3.4), duration: 0.4 }}
              >
                Drone
              </motion.text>
            )}
          </g>
        </motion.g>

        {/* ---- Phase 4: satellite pass, then a slow loop across the sky ---- */}
        <motion.g
          initial={reduce ? false : { x: satellite.from, opacity: 0 }}
          animate={{ x: track.park, opacity: 1 }}
          transition={{
            x: { delay: satDelay, duration: satDur, ease: SAT_EASE },
            opacity: { delay: satDelay, duration: 0.2 },
          }}
        >
          <g ref={bind('sat')}>
            <g transform={`translate(0 ${track.y})`}>
              {!reduce && (
                <motion.polygon
                  points={`-4,12 4,12 ${24 * sw},${block.backY - track.y + 18} ${-24 * sw},${block.backY - track.y + 18}`}
                  fill="url(#hero-beam)"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: [0, 1, 1, 0] }}
                  transition={{ delay: satDelay, duration: satDur, times: [0, 0.12, 0.86, 1] }}
                />
              )}
              <g transform={`scale(${sw})`}>
                <rect x={-26} y={-3.5} width={17} height={7} rx={1} fill={C.rain500} />
                <rect x={9} y={-3.5} width={17} height={7} rx={1} fill={C.rain500} />
                <path d="M-20.3 -3.5V3.5M-14.7 -3.5V3.5M14.7 -3.5V3.5M20.3 -3.5V3.5" stroke={C.surface} strokeWidth={0.8} opacity={0.7} />
                <path d="M-9 0H-7M7 0H9" stroke={C.inkSoft} strokeWidth={1.2} />
                <rect x={-7} y={-5.5} width={14} height={11} rx={2.2} fill={C.inkSoft} />
                <path d="M0 5.5V10" stroke={C.inkSoft} strokeWidth={1.2} />
                <circle cx={0} cy={11} r={1.8} fill={C.inkSoft} />
              </g>
            </g>
          </g>
        </motion.g>

        {/* ---- Phase 5: signal nodes and converging lines ----------------- */}
        {scene.lines.map((line, i) => (
          <motion.path
            key={line.key}
            ref={line.key === 'drone' ? bind('droneLine') : undefined}
            d={line.d}
            fill="none"
            stroke={line.color}
            strokeWidth={1.6 * sw}
            strokeLinecap="round"
            initial={reduce ? false : { pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 0.85 }}
            transition={{
              pathLength: { delay: T(3.35 + i * 0.09), duration: D(0.7), ease: EASE_OUT },
              opacity: { delay: T(3.35 + i * 0.09), duration: 0.1 },
            }}
          />
        ))}
        <g ref={bind('link')}>
          <motion.path
            ref={bind('linkPath')}
            d={scene.downlink}
            fill="none"
            stroke={C.leaf400}
            strokeWidth={1.3 * sw}
            strokeDasharray={`${2 * sw} ${5 * sw}`}
            strokeLinecap="round"
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: 0.8 }}
            transition={{ delay: T(3.3), duration: D(0.4) }}
          />
          {ambient && <DataDot ref={bind('linkDot')} color={C.leaf500} sw={sw} />}
        </g>
        {ambient && <DataDot ref={bind('droneDot')} color={C.sun500} sw={sw} />}

        {/* Ambient data dots: each rides one flow path on a loop (SMIL keeps it off the React render path). */}
        {ambient &&
          flows.map((flow) => (
            <g key={`dot-${flow.key}`} opacity={0}>
              <circle r={6 * sw} fill={flow.color} opacity={0.18} />
              <circle r={2.6 * sw} fill={flow.color} />
              <animateMotion
                path={flow.d}
                dur={`${flow.dur}s`}
                begin={`${flow.begin}s`}
                repeatCount="indefinite"
                calcMode="spline"
                keyPoints="0;1"
                keyTimes="0;1"
                keySplines="0.45 0 0.55 1"
              />
              <animate
                attributeName="opacity"
                values="0;1;1;0"
                keyTimes="0;0.12;0.84;1"
                dur={`${flow.dur}s`}
                begin={`${flow.begin}s`}
                repeatCount="indefinite"
              />
            </g>
          ))}

        {nodeList.map((node, i) => {
          const delay = T(3.15 + i * 0.1);
          return (
            <g key={node.label}>
              <motion.circle
                cx={node.x}
                cy={node.y}
                r={13 * sw}
                fill={node.color}
                style={{ originX: 0.5, originY: 0.5 }}
                initial={reduce ? false : { scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 0.14 }}
                transition={{ delay, duration: D(0.5), ease: EASE_OUT }}
              />
              {!reduce && (
                <motion.circle
                  cx={node.x}
                  cy={node.y}
                  r={6 * sw}
                  fill="none"
                  stroke={node.color}
                  strokeWidth={1.2}
                  style={{ originX: 0.5, originY: 0.5 }}
                  initial={{ scale: 1, opacity: 0 }}
                  animate={{ scale: 3.4, opacity: [0, 0.6, 0] }}
                  transition={{ delay: delay + 0.1, duration: D(0.9), ease: EASE_OUT }}
                />
              )}
              {ambient && (
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={7 * sw}
                  fill="none"
                  stroke={node.color}
                  strokeWidth={1.2}
                  className="ss-emit"
                  style={{ animationDelay: `${2.5 + i * 3.1}s` }}
                />
              )}
              <motion.circle
                cx={node.x}
                cy={node.y}
                r={5.5 * sw}
                fill={node.color}
                stroke={C.surface}
                strokeWidth={2 * sw}
                style={{ originX: 0.5, originY: 0.5 }}
                initial={reduce ? false : { scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay, duration: D(0.4), ease: [0.34, 1.56, 0.64, 1] }}
              />
              {cfg.labels && (
                <motion.text
                  x={node.labelSide === 'left' ? node.x - 14 : node.x + 14}
                  y={node.y + 4}
                  textAnchor={node.labelSide === 'left' ? 'end' : 'start'}
                  className="fill-muted text-[12px] font-medium"
                  initial={reduce ? false : { opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: delay + 0.15, duration: 0.4 }}
                >
                  {node.label}
                </motion.text>
              )}
            </g>
          );
        })}

        {/* ---- Phase 6: SoilSignal hub resolves the signal into a forecast - */}
        <motion.circle
          cx={hub.x}
          cy={hub.y}
          r={hub.r + 14}
          fill={C.leaf100}
          style={{ originX: 0.5, originY: 0.5 }}
          initial={reduce ? false : { scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 0.75 }}
          transition={{ delay: T(3.95), duration: D(0.6), ease: EASE_OUT }}
        />
        {ambient && (
          <circle cx={hub.x} cy={hub.y} r={hub.r} fill="none" stroke={C.leaf400} strokeWidth={1.2} className="ss-emit" />
        )}
        <motion.g
          style={{ originX: 0.5, originY: 0.5 }}
          initial={reduce ? false : { scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: T(3.2), duration: D(0.5), ease: EASE_OUT }}
        >
          <circle cx={hub.x} cy={hub.y} r={hub.r} fill={C.surface} stroke={C.lineStrong} strokeWidth={1} />
          <g transform={`translate(${hub.x - hub.r * 0.62} ${hub.y - hub.r * 0.62}) scale(${(hub.r * 1.24) / 32})`}>
            <MarkShapes />
          </g>
        </motion.g>

        <motion.path
          d={forecast.connector}
          fill="none"
          stroke={C.leaf500}
          strokeWidth={1.6 * sw}
          strokeLinecap="round"
          initial={reduce ? false : { pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 0.85 }}
          transition={{ pathLength: { delay: T(4.05), duration: D(0.3), ease: 'easeOut' }, opacity: { delay: T(4.05), duration: 0.05 } }}
        />

        <motion.g
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: T(3.95), duration: D(0.5), ease: EASE_OUT }}
        >
          <rect
            x={card.x}
            y={card.y}
            width={card.w}
            height={card.h}
            rx={cfg.labels ? 14 : 18}
            fill={C.surface}
            stroke={C.line}
            filter="url(#hero-card-shadow)"
          />
          <text
            x={forecast.chart.left}
            y={card.y + (cfg.labels ? 30 : 38)}
            className={`fill-muted font-medium ${cfg.labels ? 'text-[12px]' : 'text-[21px]'}`}
          >
            {cfg.labels ? 'Yield forecast' : 'Yield'}
          </text>
          {forecast.grid.map((y) => (
            <line key={y} x1={forecast.chart.left} x2={forecast.chart.right} y1={y} y2={y} stroke={C.line} strokeWidth={1} />
          ))}
          {cfg.labels &&
            forecast.months.map((m) => (
              <text key={m.label} x={m.x} y={card.y + card.h - 14} textAnchor="middle" className="data fill-faint text-[10.5px]">
                {m.label}
              </text>
            ))}
        </motion.g>

        <motion.path
          fill="url(#hero-band)"
          initial={reduce ? false : { d: forecast.bandCollapsed, opacity: 0 }}
          animate={{ d: forecast.band, opacity: 1 }}
          transition={{ delay: T(4.3), duration: D(0.75), ease: EASE_OUT }}
        />
        <motion.path
          d={forecast.line}
          fill="none"
          stroke={C.leaf700}
          strokeWidth={2.4 * sw}
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={reduce ? false : { pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{
            pathLength: { delay: T(4.2), duration: D(0.8), ease: EASE_OUT },
            opacity: { delay: T(4.2), duration: 0.05 },
          }}
        />
        {ambient && <path d={forecast.band} fill={C.leaf300} className="ss-glow" />}
        <motion.g
          initial={reduce ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: T(4.7), duration: D(0.5), ease: EASE_OUT }}
        >
          <text
            x={forecast.chart.left}
            y={card.y + (cfg.labels ? 62 : 82)}
            className={`data fill-ink font-semibold ${cfg.labels ? 'text-[28px]' : 'text-[40px]'}`}
          >
            {forecast.value}
            <tspan dx={cfg.labels ? 6 : 7} className={`fill-faint font-normal ${cfg.labels ? 'text-[12px]' : 'text-[18px]'}`}>
              bu/ac
            </tspan>
          </text>
          {cfg.labels && (
            <text x={forecast.chart.right} y={card.y + 62} textAnchor="end" className="data fill-leaf-700 text-[12px]">
              ±{forecast.range}
            </text>
          )}
        </motion.g>
        <motion.circle
          cx={forecast.end.x}
          cy={forecast.end.y}
          r={4.4 * sw}
          fill={C.leaf700}
          stroke={C.surface}
          strokeWidth={2 * sw}
          style={{ originX: 0.5, originY: 0.5 }}
          initial={reduce ? false : { scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: T(4.9), duration: D(0.35), ease: [0.34, 1.56, 0.64, 1] }}
        />
      </svg>
    </motion.div>
  );
}
