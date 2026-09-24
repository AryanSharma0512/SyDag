import { motion, useReducedMotion, type Variants } from 'motion/react';
import { EASE_OUT } from '../../utils/motion';
import { PALETTE as C } from '../../utils/palette';

const draw = (delay: number, duration = 0.8): Variants => ({
  hidden: { pathLength: 0, opacity: 0 },
  shown: {
    pathLength: 1,
    opacity: 1,
    transition: { pathLength: { delay, duration, ease: EASE_OUT }, opacity: { delay, duration: 0.1 } },
  },
});

const pop = (delay: number): Variants => ({
  hidden: { scale: 0, opacity: 0 },
  shown: { scale: 1, opacity: 1, transition: { delay, duration: 0.35, ease: [0.34, 1.56, 0.64, 1] } },
});

/** A forecast line extending point by point as the season advances. */
function ProgressiveIcon() {
  const pts = [
    [8, 42],
    [20, 34],
    [33, 25],
    [47, 17],
  ];
  return (
    <svg width="56" height="56" viewBox="0 0 56 56" fill="none" aria-hidden="true">
      <path d="M6 48H50" stroke={C.line} strokeWidth={1.5} strokeLinecap="round" />
      <motion.path
        d="M8 42C13 39 16 36.5 20 34S28 28.4 33 25S42 19.6 47 17"
        stroke={C.leaf700}
        strokeWidth={2.2}
        strokeLinecap="round"
        variants={draw(0.1, 1.1)}
      />
      {pts.map(([x, y], i) => (
        <motion.circle
          key={i}
          cx={x}
          cy={y}
          r={3.2}
          fill={i === pts.length - 1 ? C.leaf700 : C.surface}
          stroke={C.leaf700}
          strokeWidth={1.8}
          style={{ originX: 0.5, originY: 0.5 }}
          variants={pop(0.2 + i * 0.26)}
        />
      ))}
    </svg>
  );
}

/** An interval band that narrows as observations accumulate. */
function UncertaintyIcon() {
  const wide = 'M6 20C18 20 38 20 50 20L50 40C38 40 18 40 6 40Z';
  const narrowing = 'M6 16C18 20 38 27 50 28L50 32C38 33 18 40 6 44Z';
  return (
    <svg width="56" height="56" viewBox="0 0 56 56" fill="none" aria-hidden="true">
      <motion.path
        fill={C.leaf400}
        variants={{
          hidden: { d: wide, opacity: 0 },
          shown: {
            d: [wide, wide, narrowing],
            opacity: [0, 0.18, 0.18],
            transition: { duration: 1.4, times: [0, 0.25, 1], ease: EASE_OUT, delay: 0.1 },
          },
        }}
      />
      <motion.path d="M6 30C18 30 38 30 50 30" stroke={C.leaf700} strokeWidth={2.2} strokeLinecap="round" variants={draw(0.15, 0.9)} />
      <motion.circle
        cx={50}
        cy={30}
        r={3.2}
        fill={C.leaf700}
        stroke={C.surface}
        strokeWidth={1.6}
        style={{ originX: 0.5, originY: 0.5 }}
        variants={pop(1.2)}
      />
    </svg>
  );
}

/** Crop, weather and soil context converging on one reading. */
function ContextIcon() {
  const nodes = [
    { x: 11, y: 13, color: C.rain500 },
    { x: 46, y: 15, color: C.leaf500 },
    { x: 14, y: 45, color: C.soil500 },
  ];
  return (
    <svg width="56" height="56" viewBox="0 0 56 56" fill="none" aria-hidden="true">
      {nodes.map((n, i) => (
        <motion.path
          key={i}
          d={`M${n.x} ${n.y}Q${(n.x + 30) / 2 + (i === 1 ? 4 : -4)} ${(n.y + 30) / 2} 30 30`}
          stroke={n.color}
          strokeWidth={1.7}
          strokeLinecap="round"
          variants={draw(0.35 + i * 0.12, 0.6)}
        />
      ))}
      {nodes.map((n, i) => (
        <motion.circle
          key={`n-${i}`}
          cx={n.x}
          cy={n.y}
          r={3.6}
          fill={n.color}
          stroke={C.surface}
          strokeWidth={1.6}
          style={{ originX: 0.5, originY: 0.5 }}
          variants={pop(0.1 + i * 0.1)}
        />
      ))}
      <motion.circle
        cx={30}
        cy={30}
        r={11}
        fill={C.leaf100}
        style={{ originX: 0.5, originY: 0.5 }}
        variants={{
          hidden: { scale: 0.4, opacity: 0 },
          shown: { scale: 1, opacity: 1, transition: { delay: 0.95, duration: 0.5, ease: EASE_OUT } },
        }}
      />
      <motion.circle cx={30} cy={30} r={5} fill={C.leaf700} style={{ originX: 0.5, originY: 0.5 }} variants={pop(0.85)} />
    </svg>
  );
}

const PRINCIPLES = [
  {
    title: 'Progressive',
    body: 'Forecasts evolve as the season develops.',
    Icon: ProgressiveIcon,
  },
  {
    title: 'Uncertain, not opaque',
    body: 'Prediction intervals communicate what the model does and does not know.',
    Icon: UncertaintyIcon,
  },
  {
    title: 'Context-aware',
    body: 'Crop observations can be interpreted alongside weather, soil, and historical context.',
    Icon: ContextIcon,
  },
];

export function Principles() {
  const reduce = useReducedMotion();
  return (
    <section className="mx-auto max-w-6xl px-4 pt-14 pb-20 sm:px-6 sm:pt-20 sm:pb-24" aria-labelledby="principles-heading">
      <h2 id="principles-heading" className="sr-only">
        Principles
      </h2>
      <div className="grid gap-12 md:grid-cols-3 md:gap-10">
        {PRINCIPLES.map(({ title, body, Icon }, i) => (
          <motion.div
            key={title}
            className="border-t border-line pt-8"
            initial={reduce ? 'shown' : 'hidden'}
            whileInView="shown"
            viewport={{ once: true, margin: '0px 0px -12% 0px' }}
            variants={{
              hidden: { opacity: 0, y: 12 },
              shown: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE_OUT, delay: i * 0.08 } },
            }}
          >
            <Icon />
            <h3 className="mt-6 text-[18px] font-semibold tracking-[-0.015em] text-ink">{title}</h3>
            <p className="mt-2 max-w-xs text-[15px] leading-relaxed text-pretty text-muted">{body}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
