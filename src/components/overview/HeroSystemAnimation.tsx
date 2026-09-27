import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react';
import { useMediaQuery } from '../../utils/hooks';
import { bandPath, monotonePath, scaleLinear, type Pt } from '../../utils/chart';
import { EASE_OUT } from '../../utils/motion';
import { PALETTE as C } from '../../utils/palette';
import { MarkShapes } from '../brand/SignalMark';

/**
 * The SoilSignal story in one scene, played once (~5s desktop, ~3.6s mobile):
 *   1. seeds and roots appear in a soil cross-section
 *   2. maize emerges and sets tassels and ears
 *   3. fine rain traces pass through, and a drone flies in over the canopy
 *   4. a satellite pass sweeps the field and lights up field zones
 *   5. satellite, drone, weather and field-record nodes activate and feed SoilSignal
 *   6. the signal resolves into a yield forecast curve and value
 * Afterwards only ambient motion remains: the drone hovers and scans, data dots
 * travel into SoilSignal and on to the forecast, nodes pulse, leaves shift and
 * the contours drift.
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
  satellite: { y: number; from: number; to: number };
  /** Where the drone hovers, and the canopy height its scan beam reaches. */
  drone: { x: number; y: number; scale: number; beamTo: number; beamWidth: number };
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
  satellite: { y: 50, from: -90, to: 716 },
  drone: { x: 470, y: 122, scale: 1.4, beamTo: 238, beamWidth: 60 },
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
  satellite: { y: 44, from: -80, to: 430 },
  drone: { x: 124, y: 164, scale: 1.7, beamTo: 262, beamWidth: 72 },
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
function flowPath(from: Pt, to: Pt) {
  const dx = to.x - from.x;
  return `M${round(from.x)},${round(from.y)} C${round(from.x + dx * 0.55)},${round(from.y)} ${round(to.x - dx * 0.45)},${round(to.y)} ${round(to.x)},${round(to.y)}`;
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

  const { hub, card, nodes, drone, satellite, arrivals } = cfg;
  const arrive = (dy: number): Pt => ({ x: hub.x - hub.r - 1, y: hub.y + dy });
  const lines = [
    { key: 'spectral', color: nodes.spectral.color, d: flowPath(nodes.spectral, arrive(arrivals.spectral)) },
    { key: 'weather', color: nodes.weather.color, d: flowPath(nodes.weather, arrive(arrivals.weather)) },
    {
      key: 'drone',
      color: C.sun500,
      d: flowPath({ x: drone.x + 4 * drone.scale, y: drone.y + 3 * drone.scale }, arrive(arrivals.drone)),
    },
    { key: 'soil', color: nodes.soil.color, d: flowPath(nodes.soil, arrive(arrivals.soil)) },
  ];
  // The satellite, parked after its pass, beams down to its imagery node.
  const downlink = `M${satellite.to},${satellite.y + 14 * cfg.stroke}L${nodes.spectral.x},${nodes.spectral.y - 8 * cfg.stroke}`;

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

  const ambient = settled && !reduce;

  // Scroll: the field system gently compresses as the product section takes over.
  const { scrollY } = useScroll();
  const scaleY = useTransform(scrollY, [0, 620], [1, 0.9]);
  const scaleX = useTransform(scrollY, [0, 620], [1, 0.97]);
  const opacity = useTransform(scrollY, [0, 520], [1, 0.4]);
  const lift = useTransform(scrollY, [0, 620], [0, -24]);

  const { block, satellite, nodes, hub, card, drone } = cfg;
  const { forecast } = scene;
  const sw = cfg.stroke;
  const satDelay = T(2.35);
  const satDur = D(1.15);

  const nodeList = [nodes.spectral, nodes.weather, nodes.soil];
  const beamDepth = drone.beamTo - drone.y;
  const ds = drone.scale;
  const beamPoints = `${-5 * ds},${9 * ds} ${5 * ds},${9 * ds} ${drone.beamWidth},${beamDepth} ${-drone.beamWidth},${beamDepth}`;
  // Everything the ambient data dots travel along: sources into the hub, the satellite downlink, the hub out to the forecast.
  const flows = [
    ...scene.lines.map((line, i) => ({ key: line.key, d: line.d, color: line.color, dur: 3.2, begin: 0.4 + i * 0.8 })),
    { key: 'downlink', d: scene.downlink, color: C.leaf500, dur: 1.8, begin: 1.1 },
    { key: 'forecast', d: forecast.connector, color: C.leaf700, dur: 1.6, begin: 0.2 },
  ];

  return (
    <motion.div
      className="relative w-full select-none"
      style={{
        aspectRatio: `${cfg.w} / ${cfg.h}`,
        ...(reduce ? {} : { scaleX, scaleY, opacity, y: lift, originY: 1 }),
      }}
      role="img"
      aria-label="Illustration: a maize plot is planted and grows ears, rain passes, a drone scans the canopy and a satellite images the plot. Satellite and drone imagery, weather and the field record feed SoilSignal, which produces a yield forecast."
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
            <stop offset="100%" stopColor={C.leaf300} stopOpacity="0.06" />
          </linearGradient>
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
          const progress = (cell.cx - satellite.from) / (satellite.to - satellite.from);
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

        {/* ---- Drone: flies in over the canopy, then hovers and scans ------ */}
        <motion.g
          initial={reduce ? false : { x: -drone.x - 60 * ds, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ x: { delay: T(1.55), duration: D(1.4), ease: EASE_OUT }, opacity: { delay: T(1.55), duration: 0.3 } }}
        >
          <g transform={`translate(${drone.x} ${drone.y})`}>
            <motion.g
              initial={reduce ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: T(2.8), duration: D(0.5), ease: 'easeOut' }}
            >
              <clipPath id="hero-drone-clip">
                <polygon points={beamPoints} />
              </clipPath>
              <polygon points={beamPoints} fill="url(#hero-drone-beam)" />
              <ellipse cx={0} cy={beamDepth} rx={drone.beamWidth} ry={drone.beamWidth * 0.14} fill={C.leaf300} opacity={0.3} />
              {ambient && (
                <g clipPath="url(#hero-drone-clip)">
                  <rect
                    x={-drone.beamWidth}
                    y={8 * ds}
                    width={drone.beamWidth * 2}
                    height={1.6 * sw}
                    fill={C.leaf400}
                    className="ss-scan"
                    style={{ '--scan': `${beamDepth - 10 * ds}px` } as CSSProperties}
                  />
                </g>
              )}
            </motion.g>
            <g className={ambient ? 'ss-hover' : undefined}>
              <g transform={`scale(${ds})`}>
                <DroneShape spin={!reduce} />
              </g>
            </g>
            {cfg.labels && (
              <motion.text
                x={-38 * ds}
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

        {/* ---- Phase 4: satellite pass ----------------------------------- */}
        <motion.g
          initial={reduce ? false : { x: satellite.from, opacity: 0 }}
          animate={{ x: satellite.to, opacity: 1 }}
          transition={{
            x: { delay: satDelay, duration: satDur, ease: SAT_EASE },
            opacity: { delay: satDelay, duration: 0.2 },
          }}
        >
          <g transform={`translate(0 ${satellite.y})`}>
            {!reduce && (
              <motion.polygon
                points={`-4,12 4,12 ${24 * sw},${block.backY - satellite.y + 18} ${-24 * sw},${block.backY - satellite.y + 18}`}
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
        </motion.g>

        {/* ---- Phase 5: signal nodes and converging lines ----------------- */}
        {scene.lines.map((line, i) => (
          <motion.path
            key={line.key}
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
        <motion.path
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
