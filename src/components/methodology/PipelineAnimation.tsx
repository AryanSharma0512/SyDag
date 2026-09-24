import { useRef } from 'react';
import { motion, useInView, useReducedMotion } from 'motion/react';
import { EASE_OUT } from '../../utils/motion';
import { PALETTE as C } from '../../utils/palette';

const INPUTS = [
  { label: 'Crop observations', detail: 'NDVI, NDRE', color: C.leaf500 },
  { label: 'Weather', detail: 'Rain, heat, GDD', color: C.rain500 },
  { label: 'Soil', detail: 'Water, texture', color: C.soil500 },
  { label: 'Historical context', detail: 'Regional yields', color: C.inkSoft },
];

const STAGES = [
  { label: 'Feature engineering', detail: 'Season-aware signals' },
  { label: 'Yield model', detail: 'Interpretable, calibrated' },
];

/** Horizontal layout (viewBox units). */
const L = {
  input: { x: 0, w: 236, h: 58, ys: [44, 130, 216, 302] },
  feature: { x: 372, y: 145, w: 204, h: 60 },
  model: { x: 634, y: 145, w: 180, h: 60 },
  output: { x: 872, y: 118, w: 168, h: 114 },
};

const pop = (shown: boolean, reduce: boolean | null, delay: number) => ({
  initial: reduce ? false : { opacity: 0, y: 8 },
  animate: shown ? { opacity: 1, y: 0 } : undefined,
  transition: { duration: 0.45, ease: EASE_OUT, delay },
});

/**
 * The pipeline assembles itself once when scrolled into view: inputs appear,
 * connectors draw, one signal particle travels each connector, then each stage
 * lights up in turn. No looping circuit.
 */
export function PipelineAnimation() {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: '0px 0px -20% 0px' });
  const shown = inView || !!reduce;

  const featureIn = { x: L.feature.x, y: L.feature.y + L.feature.h / 2 };
  const inputPaths = L.input.ys.map((y, i) => {
    const from = { x: L.input.x + L.input.w, y };
    const to = { x: featureIn.x, y: featureIn.y + (i - 1.5) * 7 };
    const dx = to.x - from.x;
    return `M${from.x},${from.y} C${from.x + dx * 0.55},${from.y} ${to.x - dx * 0.45},${to.y} ${to.x},${to.y}`;
  });
  const midY = L.feature.y + L.feature.h / 2;
  const toModel = `M${L.feature.x + L.feature.w},${midY} L${L.model.x},${midY}`;
  const toOutput = `M${L.model.x + L.model.w},${midY} L${L.output.x},${midY}`;

  const draw = (delay: number, duration = 0.6) => ({
    initial: reduce ? false : { pathLength: 0, opacity: 0 },
    animate: shown ? { pathLength: 1, opacity: 1 } : undefined,
    transition: { pathLength: { delay, duration, ease: EASE_OUT }, opacity: { delay, duration: 0.05 } },
  });

  const particle = (d: string, color: string, delay: number, key: string) =>
    reduce ? null : (
      <motion.path
        key={key}
        d={d}
        pathLength={100}
        fill="none"
        stroke={color}
        strokeWidth={4}
        strokeLinecap="round"
        strokeDasharray="4 100"
        initial={{ strokeDashoffset: 104, opacity: 0 }}
        animate={shown ? { strokeDashoffset: 0, opacity: [0, 1, 1, 0] } : undefined}
        transition={{ delay, duration: 0.8, ease: 'easeInOut', opacity: { delay, duration: 0.8, times: [0, 0.1, 0.8, 1] } }}
      />
    );

  // Mini forecast inside the output node.
  const out = L.output;
  const curve = `M${out.x + 18},${out.y + 88} C${out.x + 60},${out.y + 80} ${out.x + 86},${out.y + 58} ${out.x + 110},${out.y + 52} S${out.x + 140},${out.y + 48} ${out.x + 150},${out.y + 47}`;
  const band = `M${out.x + 18},${out.y + 70} C${out.x + 60},${out.y + 64} ${out.x + 90},${out.y + 48} ${out.x + 150},${out.y + 42} L${out.x + 150},${out.y + 53} C${out.x + 90},${out.y + 60} ${out.x + 60},${out.y + 96} ${out.x + 18},${out.y + 104} Z`;

  return (
    <div ref={ref}>
      {/* Large screens: horizontal flow */}
      <svg viewBox="0 0 1040 346" className="hidden h-auto w-full lg:block" role="img" aria-label="Pipeline: crop observations, weather, soil and historical context feed feature engineering, then the yield model, which produces a progressive forecast.">
        {inputPaths.map((d, i) => (
          <g key={d}>
            <path d={d} fill="none" stroke={C.line} strokeWidth={1.5} />
            <motion.path d={d} fill="none" stroke={INPUTS[i].color} strokeWidth={1.6} strokeLinecap="round" {...draw(0.55 + i * 0.08)} />
            {particle(d, INPUTS[i].color, 1.05 + i * 0.1, `p-${i}`)}
          </g>
        ))}
        <path d={toModel} stroke={C.line} strokeWidth={1.5} />
        <motion.path d={toModel} stroke={C.leaf600} strokeWidth={1.6} {...draw(1.5, 0.35)} />
        {particle(toModel, C.leaf600, 1.65, 'p-model')}
        <path d={toOutput} stroke={C.line} strokeWidth={1.5} />
        <motion.path d={toOutput} stroke={C.leaf600} strokeWidth={1.6} {...draw(2.0, 0.35)} />
        {particle(toOutput, C.leaf600, 2.15, 'p-out')}

        {INPUTS.map((input, i) => {
          const y = L.input.ys[i] - L.input.h / 2;
          return (
            <motion.g key={input.label} {...pop(shown, reduce, i * 0.12)}>
              <rect x={L.input.x + 0.5} y={y} width={L.input.w - 1} height={L.input.h} rx={14} fill={C.surface} stroke={C.line} />
              <circle cx={L.input.x + 26} cy={L.input.ys[i]} r={5} fill={input.color} />
              <text x={L.input.x + 44} y={L.input.ys[i] - 3} className="fill-ink text-[14px] font-medium">
                {input.label}
              </text>
              <text x={L.input.x + 44} y={L.input.ys[i] + 15} className="fill-muted text-[12px]">
                {input.detail}
              </text>
            </motion.g>
          );
        })}

        {[L.feature, L.model].map((node, i) => (
          <motion.g key={STAGES[i].label} {...pop(shown, reduce, 1.0 + i * 0.5)}>
            <rect x={node.x + 0.5} y={node.y} width={node.w - 1} height={node.h} rx={14} fill={C.surface} stroke={C.lineStrong} />
            <text x={node.x + node.w / 2} y={node.y + 26} textAnchor="middle" className="fill-ink text-[14px] font-medium">
              {STAGES[i].label}
            </text>
            <text x={node.x + node.w / 2} y={node.y + 44} textAnchor="middle" className="fill-muted text-[12px]">
              {STAGES[i].detail}
            </text>
          </motion.g>
        ))}

        <motion.g {...pop(shown, reduce, 2.1)}>
          <rect x={out.x + 0.5} y={out.y} width={out.w - 1} height={out.h} rx={16} fill={C.leaf50} stroke={C.leaf200} />
          <text x={out.x + 18} y={out.y + 28} className="fill-leaf-800 text-[14px] font-medium">
            Progressive forecast
          </text>
          <motion.path
            d={band}
            fill={C.leaf400}
            initial={reduce ? false : { opacity: 0 }}
            animate={shown ? { opacity: 0.18 } : undefined}
            transition={{ delay: 2.45, duration: 0.6 }}
          />
          <motion.path d={curve} fill="none" stroke={C.leaf700} strokeWidth={2.2} strokeLinecap="round" {...draw(2.35, 0.8)} />
        </motion.g>
      </svg>

      {/* Small screens: the same pipeline as a vertical flow */}
      <div className="lg:hidden">
        <div className="grid grid-cols-2 gap-2.5">
          {INPUTS.map((input, i) => (
            <motion.div key={input.label} className="rounded-xl border border-line bg-surface px-3.5 py-3" {...pop(shown, reduce, i * 0.1)}>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full" style={{ background: input.color }} aria-hidden="true" />
                <span className="text-[14px] font-medium text-ink">{input.label}</span>
              </div>
              <div className="mt-0.5 pl-4 text-[12px] text-muted">{input.detail}</div>
            </motion.div>
          ))}
        </div>
        {[...STAGES, { label: 'Progressive forecast', detail: 'Updated as the season unfolds' }].map((stage, i) => (
          <div key={stage.label} className="flex flex-col items-center">
            <div className="relative h-9 w-px bg-line" aria-hidden="true">
              <motion.div
                className="absolute inset-0 origin-top bg-leaf-600"
                initial={reduce ? false : { scaleY: 0 }}
                animate={shown ? { scaleY: 1 } : undefined}
                transition={{ delay: 0.5 + i * 0.45, duration: 0.35, ease: EASE_OUT }}
              />
              {!reduce && (
                <motion.span
                  className="absolute -left-[3px] h-[7px] w-[7px] rounded-full bg-leaf-600"
                  initial={{ y: -4, opacity: 0 }}
                  animate={shown ? { y: [0, 30], opacity: [0, 1, 0] } : undefined}
                  transition={{ delay: 0.6 + i * 0.45, duration: 0.6, ease: 'easeInOut' }}
                />
              )}
            </div>
            <motion.div
              className={`w-full rounded-xl border px-4 py-3 text-center ${
                i === 2 ? 'border-leaf-200 bg-leaf-50' : 'border-line-strong bg-surface'
              }`}
              {...pop(shown, reduce, 0.8 + i * 0.45)}
            >
              <div className={`text-[14px] font-medium ${i === 2 ? 'text-leaf-800' : 'text-ink'}`}>{stage.label}</div>
              <div className="mt-0.5 text-[12px] text-muted">{stage.detail}</div>
            </motion.div>
          </div>
        ))}
      </div>
    </div>
  );
}
