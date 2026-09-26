import { useEffect, useMemo, useState } from 'react';
import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react';
import { useMediaQuery } from '../../utils/hooks';
import { bandPath, monotonePath, scaleLinear, type Pt } from '../../utils/chart';
import { EASE_OUT } from '../../utils/motion';
import { PALETTE as C } from '../../utils/palette';
import { MARK_PATHS } from '../brand/SignalMark';

/**
 * The SoilSignal story in one scene, played once (~5s desktop, ~3.6s mobile):
 *   1. seeds and roots appear in a soil cross-section
 *   2. crop shoots emerge
 *   3. fine rain traces pass through
 *   4. a satellite pass sweeps the field and lights up field zones
 *   5. soil, weather and spectral signal nodes activate and converge on SoilSignal
 *   6. the signal resolves into a yield forecast curve
 * Afterwards only ambient motion remains: an occasional leaf shift, one data
 * pulse, a slow contour drift and a signal emission every ~10s.
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
  nodes: { spectral: NodeSpec; weather: NodeSpec; soil: NodeSpec };
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
  nodes: {
    spectral: { x: 700, y: 132, label: 'Spectral', color: C.leaf500, labelSide: 'left' },
    weather: { x: 236, y: 188, label: 'Weather', color: C.rain500, labelSide: 'left' },
    soil: { x: 478, y: 466, label: 'Soil', color: C.soil500, labelSide: 'left' },
  },
  hub: { x: 848, y: 232, r: 25 },
  card: { x: 902, y: 88, w: 270, h: 222 },
  cells: [12, 3],
  labels: true,
  time: 1,
  stroke: 1,
};

const MOBILE: SceneConfig = {
  w: 720,
  h: 560,
  block: { x0: 16, x1: 404, frontY: 384, backY: 344, skew: 40, bottom: 542 },
  horizons: [430, 484],
  frontRow: 6,
  backRow: 0,
  plantHeight: [92, 122],
  rain: 10,
  satellite: { y: 58, from: -80, to: 398 },
  nodes: {
    spectral: { x: 400, y: 148, label: 'Spectral', color: C.leaf500, labelSide: 'left' },
    weather: { x: 120, y: 210, label: 'Weather', color: C.rain500, labelSide: 'left' },
    soil: { x: 236, y: 470, label: 'Soil', color: C.soil500, labelSide: 'left' },
  },
  hub: { x: 506, y: 270, r: 30 },
  card: { x: 552, y: 150, w: 158, h: 236 },
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

/** A corn-like plant: a gently leaning stem with alternating arching blades. */
function plantGeometry(x: number, base: number, height: number, seed: number) {
  const lean = Math.sin(seed * 2.3) * 3;
  const stem = `M${round(x)},${round(base)} C${round(x + lean * 0.2)},${round(base - height * 0.45)} ${round(x + lean * 0.8)},${round(base - height * 0.75)} ${round(x + lean)},${round(base - height)}`;
  const leaves: string[] = [];
  for (let k = 0; k < 4; k++) {
    const t = 0.26 + k * 0.18;
    const ay = base - height * t;
    const ax = x + lean * t;
    const dir = (k + seed) % 2 === 0 ? 1 : -1;
    const len = height * (0.5 - k * 0.075);
    const rise = len * 0.42;
    leaves.push(
      `M${round(ax)},${round(ay)} C${round(ax + dir * len * 0.3)},${round(ay - rise)} ${round(ax + dir * len * 0.72)},${round(ay - rise * 0.95)} ${round(ax + dir * len)},${round(ay - rise * 0.35)}`,
    );
  }
  return { stem, leaves };
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

  const { hub, card, nodes } = cfg;
  const arrive = (dy: number): Pt => ({ x: hub.x - hub.r - 1, y: hub.y + dy });
  const lines = [
    { key: 'spectral', color: nodes.spectral.color, d: flowPath(nodes.spectral, arrive(-7)) },
    { key: 'weather', color: nodes.weather.color, d: flowPath(nodes.weather, arrive(0)) },
    { key: 'soil', color: nodes.soil.color, d: flowPath(nodes.soil, arrive(7)) },
  ];

  const pad = cfg.labels ? 20 : 14;
  const chart = {
    left: card.x + pad,
    right: card.x + card.w - pad,
    top: card.y + (cfg.labels ? 70 : 34),
    bottom: card.y + card.h - (cfg.labels ? 34 : 22),
  };
  const sx = scaleLinear(0, 1, chart.left, chart.right);
  const sy = scaleLinear(125, 205, chart.bottom, chart.top);
  const mid = SEASON.t.map((t, i) => ({ x: sx(t), y: sy(SEASON.mid[i]) }));
  const hi = SEASON.t.map((t, i) => ({ x: sx(t), y: sy(SEASON.hi[i]) }));
  const lo = SEASON.t.map((t, i) => ({ x: sx(t), y: sy(SEASON.lo[i]) }));
  const forecast = {
    chart,
    line: monotonePath(mid),
    band: bandPath(hi, lo),
    bandCollapsed: bandPath(mid, mid),
    end: mid[mid.length - 1],
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

  const { block, satellite, nodes, hub, card } = cfg;
  const { forecast } = scene;
  const sw = cfg.stroke;
  const satDelay = T(2.35);
  const satDur = D(1.15);

  const nodeList = [nodes.spectral, nodes.weather, nodes.soil];

  return (
    <motion.div
      className="relative w-full select-none"
      style={{
        aspectRatio: `${cfg.w} / ${cfg.h}`,
        ...(reduce ? {} : { scaleX, scaleY, opacity, y: lift, originY: 1 }),
      }}
      role="img"
      aria-label="Illustration: a maize plot is planted and grows, rain passes and a satellite images the plot. Imagery, weather and soil feed SoilSignal, which produces a yield forecast curve."
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

        {/* ---- Phase 2: crops emerge (back row first, lighter) ----------- */}
        {[...scene.plants]
          .sort((a, b) => (a.row === b.row ? 0 : a.row === 'back' ? -1 : 1))
          .map((p, i) => {
            const geo = plantGeometry(p.x, p.base, p.height, p.seed);
            const back = p.row === 'back';
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
                    strokeWidth={(back ? 1.8 : 2.4) * sw}
                    strokeLinecap="round"
                  />
                  {geo.leaves.map((d, k) => (
                    <motion.path
                      key={k}
                      d={d}
                      fill="none"
                      stroke={back ? C.leaf200 : k > 1 ? C.leaf500 : C.leaf700}
                      strokeWidth={(back ? 1.7 : 2.3) * sw}
                      strokeLinecap="round"
                      initial={reduce ? false : { pathLength: 0 }}
                      animate={{ pathLength: 1 }}
                      transition={{ delay: delay + T(0.18 + k * 0.08), duration: D(0.5), ease: EASE_OUT }}
                    />
                  ))}
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
        {ambient &&
          scene.lines.map((line, i) => (
            <path
              key={`pulse-${line.key}`}
              d={line.d}
              pathLength={100}
              fill="none"
              stroke={line.color}
              strokeWidth={3 * sw}
              strokeLinecap="round"
              className="ss-travel"
              style={{ animationDelay: `${1.5 + i * 3}s` }}
            />
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
            <path d={MARK_PATHS.horizonTop} stroke={C.soil500} strokeWidth={2.6} strokeLinecap="round" />
            <path d={MARK_PATHS.horizonLow} stroke={C.soil500} strokeWidth={2.6} strokeLinecap="round" opacity={0.5} />
            <path d={MARK_PATHS.leaf} fill={C.leaf700} />
            <path d={MARK_PATHS.arc} stroke={C.leaf700} strokeWidth={2.7} strokeLinecap="round" fill="none" />
            <path d={MARK_PATHS.echo} stroke={C.leaf700} strokeWidth={2.3} strokeLinecap="round" fill="none" opacity={0.45} />
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
          {cfg.labels && (
            <>
              <text x={forecast.chart.left} y={card.y + 30} className="fill-muted text-[12px] font-medium">
                Yield forecast
              </text>
              <text x={forecast.chart.right} y={card.y + 30} textAnchor="end" className="data fill-faint text-[11px]">
                bu/ac
              </text>
            </>
          )}
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
