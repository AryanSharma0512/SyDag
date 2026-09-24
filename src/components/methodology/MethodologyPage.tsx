import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight } from 'lucide-react';
import type { DataSource, FieldForecast, ForecastSnapshot } from '../../types/agricultural';
import { getForecast } from '../../services/forecasts';
import { getDataSources } from '../../services/sources';
import { APP_CONFIG } from '../../config/appConfig';
import { EASE_OUT } from '../../utils/motion';
import { PALETTE as C } from '../../utils/palette';
import { Link } from '../../utils/router';
import { Reveal } from '../common/Reveal';
import { DataBadge } from '../common/DataBadge';
import { PipelineAnimation } from './PipelineAnimation';
import { UncertaintyDemo } from './UncertaintyDemo';

type Phase = 'early' | 'mid' | 'late';

interface PlantSpec {
  height: number;
  leaves: number;
  leafLength: number;
  droop: number;
  stem: string;
  leafColors: string[];
  tassel?: string;
  ear?: { color: string; size: number; silk: boolean };
}

const PLANTS: Record<Phase, PlantSpec> = {
  early: { height: 46, leaves: 4, leafLength: 30, droop: 0.15, stem: C.leaf500, leafColors: [C.leaf500, C.leaf400] },
  mid: {
    height: 128,
    leaves: 8,
    leafLength: 50,
    droop: 0.3,
    stem: C.leaf700,
    leafColors: [C.leaf700, C.leaf600, C.leaf500],
    tassel: C.sun500,
    ear: { color: C.leaf400, size: 1, silk: true },
  },
  late: {
    height: 132,
    leaves: 8,
    leafLength: 47,
    droop: 0.85,
    stem: C.soil400,
    leafColors: [C.soil300, C.sun300, C.soil400],
    tassel: C.soil500,
    ear: { color: C.sun300, size: 1.25, silk: false },
  },
};

/** An SVG corn plant drawn at three maturities; it grows into place when revealed. */
function CropSilhouette({ phase, delay }: { phase: Phase; delay: number }) {
  const reduce = useReducedMotion();
  const spec = PLANTS[phase];
  const baseX = 60;
  const baseY = 160;
  const top = baseY - spec.height;
  const leaves = Array.from({ length: spec.leaves }, (_, k) => {
    const t = 0.16 + (k * 0.72) / spec.leaves;
    const ay = baseY - spec.height * t;
    const dir = k % 2 === 0 ? 1 : -1;
    const len = spec.leafLength * (1 - k * 0.05);
    const rise = len * 0.45 * (1 - spec.droop * 0.55);
    const tipY = ay - rise * 0.3 + spec.droop * len * 0.38;
    return {
      d: `M${baseX},${ay} C${baseX + dir * len * 0.35},${ay - rise} ${baseX + dir * len * 0.75},${ay - rise * 0.9} ${baseX + dir * len},${tipY}`,
      color: spec.leafColors[k % spec.leafColors.length],
    };
  });

  const show = (d: number) => ({
    initial: reduce ? (false as const) : { opacity: 0 },
    whileInView: { opacity: 1 },
    viewport: { once: true },
    transition: { delay: delay + d, duration: 0.4 },
  });

  return (
    <svg viewBox="0 0 120 176" className="h-44 w-auto" aria-hidden="true">
      <path d="M30 163H90" stroke={C.soil500} strokeWidth={2.4} strokeLinecap="round" />
      <path d="M38 169H74" stroke={C.soil500} strokeWidth={2.4} strokeLinecap="round" opacity={0.45} />
      <motion.g
        style={{ originX: 0.5, originY: 1 }}
        initial={reduce ? false : { scaleY: 0.08, opacity: 0 }}
        whileInView={{ scaleY: 1, opacity: 1 }}
        viewport={{ once: true, margin: '0px 0px -15% 0px' }}
        transition={{ delay, duration: 0.9, ease: EASE_OUT }}
      >
        <path d={`M${baseX},${baseY}L${baseX},${top}`} stroke={spec.stem} strokeWidth={3} strokeLinecap="round" />
        {leaves.map((leaf, k) => (
          <motion.path
            key={k}
            d={leaf.d}
            fill="none"
            stroke={leaf.color}
            strokeWidth={2.6}
            strokeLinecap="round"
            initial={reduce ? false : { pathLength: 0 }}
            whileInView={{ pathLength: 1 }}
            viewport={{ once: true }}
            transition={{ delay: delay + 0.3 + k * 0.05, duration: 0.55, ease: EASE_OUT }}
          />
        ))}
        {spec.ear && (
          <motion.g {...show(0.75)}>
            <ellipse
              cx={baseX + 9}
              cy={baseY - spec.height * 0.46}
              rx={5 * spec.ear.size}
              ry={12 * spec.ear.size}
              transform={`rotate(20 ${baseX + 9} ${baseY - spec.height * 0.46})`}
              fill={spec.ear.color}
            />
            {spec.ear.silk && (
              <path
                d={`M${baseX + 13},${baseY - spec.height * 0.46 - 11} q4,-6 1,-12 M${baseX + 15},${baseY - spec.height * 0.46 - 10} q6,-4 5,-11`}
                stroke={C.sun500}
                strokeWidth={1.1}
                fill="none"
                strokeLinecap="round"
              />
            )}
          </motion.g>
        )}
        {spec.tassel && (
          <motion.path
            d={`M${baseX},${top} l0,-15 M${baseX},${top - 4} l-8,-9 M${baseX},${top - 4} l8,-9 M${baseX},${top - 9} l-5,-8 M${baseX},${top - 9} l5,-8`}
            stroke={spec.tassel}
            strokeWidth={1.8}
            strokeLinecap="round"
            {...show(0.85)}
          />
        )}
      </motion.g>
    </svg>
  );
}

const PHASE_COPY: Array<{ phase: Phase; title: string; window: string; body: string }> = [
  {
    phase: 'early',
    title: 'Early season',
    window: 'May – June',
    body: 'Soil, planting context and regional history carry most of the signal. The range is wide.',
  },
  {
    phase: 'mid',
    title: 'Mid season',
    window: 'July',
    body: 'Canopy vigor and weather around pollination take over. The range narrows quickly.',
  },
  {
    phase: 'late',
    title: 'Late season',
    window: 'August – September',
    body: 'Grain fill and senescence lock in most of the outcome. The range is tight.',
  },
];

function rangeLabel(s: ForecastSnapshot | undefined) {
  return s ? `±${((s.upperBound - s.lowerBound) / 2).toFixed(1)}` : '';
}

export function MethodologyPage() {
  const reduce = useReducedMotion();
  const [forecast, setForecast] = useState<FieldForecast | null>(null);
  const [sources, setSources] = useState<DataSource[]>([]);

  useEffect(() => {
    let active = true;
    getForecast(APP_CONFIG.defaultFieldId).then((data) => active && setForecast(data));
    getDataSources().then((list) => active && setSources(list));
    return () => {
      active = false;
    };
  }, []);

  const snaps = forecast?.snapshots ?? [];
  const phaseSnapshots = [snaps[0], snaps[Math.min(APP_CONFIG.defaultDateIndex, snaps.length - 1)], snaps[snaps.length - 1]];

  return (
    <div className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
      <header className="pt-14 pb-12 sm:pt-20 sm:pb-16">
        <motion.p
          className="text-[13px] font-medium text-leaf-700"
          initial={reduce ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: EASE_OUT }}
        >
          Methodology
        </motion.p>
        <motion.h1
          className="mt-3 text-[40px] leading-[1.05] font-semibold tracking-[-0.035em] text-ink sm:text-[54px]"
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE_OUT, delay: 0.05 }}
        >
          How SoilSignal works
        </motion.h1>
        <motion.p
          className="mt-5 max-w-2xl text-[17px] leading-relaxed text-pretty text-muted sm:text-[18px]"
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE_OUT, delay: 0.12 }}
        >
          SoilSignal reads what the crop is showing alongside the conditions around it. Each new observation updates
          the forecast, and every forecast carries a range that states how certain it is.
        </motion.p>
      </header>

      <section aria-labelledby="pipeline-heading">
        <Reveal>
          <h2 id="pipeline-heading" className="text-[22px] font-semibold tracking-[-0.02em] text-ink">
            From observations to a progressive forecast
          </h2>
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
            Four kinds of evidence become season-aware features, a yield model turns them into a forecast, and the
            forecast is refreshed whenever new evidence arrives. The prototype runs on demo data to show the intended
            flow.
          </p>
        </Reveal>
        <div className="mt-10">
          <PipelineAnimation />
        </div>
      </section>

      <section className="mt-24" aria-labelledby="season-heading">
        <Reveal>
          <h2 id="season-heading" className="text-[22px] font-semibold tracking-[-0.02em] text-ink">
            The forecast matures with the crop
          </h2>
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
            Early forecasts lean on context; later forecasts lean on the crop itself.
          </p>
        </Reveal>
        <div className="relative mt-10 grid gap-12 md:grid-cols-3 md:gap-8">
          <div className="pointer-events-none absolute top-[163px] right-0 left-0 hidden h-px bg-line md:block" aria-hidden="true" />
          {PHASE_COPY.map((item, i) => (
            <div key={item.phase} className="relative">
              <div className="flex h-44 items-end">
                <CropSilhouette phase={item.phase} delay={i * 0.35} />
              </div>
              <Reveal delay={0.1 + i * 0.12} distance={8}>
                <div className="mt-6 flex items-baseline justify-between gap-4">
                  <h3 className="text-[17px] font-semibold tracking-[-0.01em] text-ink">{item.title}</h3>
                  <span className="text-[13px] text-muted">{item.window}</span>
                </div>
                <p className="mt-2 max-w-sm text-[15px] leading-relaxed text-muted">{item.body}</p>
                {phaseSnapshots[i] && (
                  <p className="mt-3 text-[13px] text-ink-soft">
                    Demo range on <span className="data">{phaseSnapshots[i]?.displayDate}</span>:{' '}
                    <span className="data font-medium text-ink">{rangeLabel(phaseSnapshots[i])}</span>{' '}
                    <span className="data text-muted">bu/ac</span>
                  </p>
                )}
              </Reveal>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-24" aria-labelledby="uncertainty-heading">
        <Reveal>
          <h2 id="uncertainty-heading" className="text-[22px] font-semibold tracking-[-0.02em] text-ink">
            Uncertain, not opaque
          </h2>
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
            Every forecast comes with a 90% range. Hover the chart or pick a phase to compare how that range behaves
            early and late in the season.
          </p>
        </Reveal>
        <Reveal className="mt-8 rounded-2xl border border-line bg-surface p-5 sm:p-8">
          {forecast ? <UncertaintyDemo forecast={forecast} /> : <div className="h-[320px]" />}
        </Reveal>
      </section>

      <section className="mt-24" aria-labelledby="sources-heading">
        <Reveal>
          <h2 id="sources-heading" className="text-[22px] font-semibold tracking-[-0.02em] text-ink">
            Data sources
          </h2>
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
            What the challenge provides, and what could enrich it. Candidate sources are not connected yet.
          </p>
        </Reveal>
        <Reveal className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[520px] text-left">
            <thead>
              <tr className="border-b border-line-strong text-[13px] text-muted">
                <th scope="col" className="py-3 pr-6 font-medium">Source</th>
                <th scope="col" className="py-3 pr-6 font-medium">Purpose</th>
                <th scope="col" className="py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id} className="border-b border-line">
                  <td className="py-3.5 pr-6 text-[15px] font-medium text-ink">{s.shortName}</td>
                  <td className="py-3.5 pr-6 text-[15px] text-ink-soft">{s.purpose}</td>
                  <td className="py-3.5">
                    <DataBadge variant={s.role === 'challenge' ? 'challenge' : 'candidate'} label={s.role === 'challenge' ? 'Challenge' : 'Candidate'} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-4 text-[13px] text-muted">
            The challenge rules and the actual dataset will determine the final integrations.
          </p>
        </Reveal>
      </section>

      <Reveal className="mt-24 flex flex-col items-start justify-between gap-6 border-t border-line pt-10 sm:flex-row sm:items-center">
        <p className="text-[18px] font-medium tracking-[-0.01em] text-ink">See it applied to a season.</p>
        <Link
          to="dashboard"
          className="lift group inline-flex items-center gap-2 rounded-full bg-leaf-700 px-5 py-2.5 text-[15px] font-medium text-white hover:bg-leaf-800 hover:shadow-lift"
        >
          Explore Forecast
          <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
        </Link>
      </Reveal>
    </div>
  );
}
