import { useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ArrowDown, ArrowUp, ChevronDown, MoveHorizontal, type LucideIcon } from 'lucide-react';
import type { FeatureImportanceItem, ModelExplanation as Driver } from '../../types/agricultural';
import { DATA_TRANSITION, EASE_OUT } from '../../utils/motion';

interface ModelExplanationProps {
  drivers: Driver[];
  featureImportance: FeatureImportanceItem[];
}

const INFLUENCE: Record<
  Driver['influence'],
  {
    label: string;
    Icon: LucideIcon;
    tone: string;
    text: string;
    from: { x?: number; y?: number };
    to: { x?: number | number[]; y?: number };
  }
> = {
  positive: {
    label: 'Positive influence',
    Icon: ArrowUp,
    tone: 'bg-leaf-50 text-leaf-700 ring-leaf-200',
    text: 'text-leaf-700',
    from: { y: 7 },
    to: { y: 0 },
  },
  negative: {
    label: 'Negative influence',
    Icon: ArrowDown,
    tone: 'bg-stress-50 text-stress-600 ring-stress-100',
    text: 'text-stress-600',
    from: { y: -7 },
    to: { y: 0 },
  },
  neutral: {
    label: 'Buffering influence',
    Icon: MoveHorizontal,
    tone: 'bg-soil-50 text-soil-600 ring-soil-200',
    text: 'text-soil-600',
    from: { x: -4 },
    to: { x: [-4, 3, 0] },
  },
};

export function ModelExplanation({ drivers, featureImportance }: ModelExplanationProps) {
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(false);
  const top = drivers.slice(0, 3);
  const features = [...featureImportance].sort((a, b) => b.weight - a.weight);
  const maxWeight = Math.max(1, ...features.map((f) => f.weight));

  return (
    <section aria-labelledby="drivers-heading">
      <h2 id="drivers-heading" className="text-[20px] font-semibold tracking-[-0.02em] text-ink">
        What is shaping this forecast?
      </h2>
      <p className="mt-1.5 text-[14px] text-muted">
        Signals associated with the current forecast. Associations, not proof of cause.
      </p>

      <div className="mt-6 grid gap-6 md:grid-cols-3 md:gap-0 md:divide-x md:divide-line">
        <AnimatePresence initial={false} mode="popLayout">
          {top.map((driver, i) => {
            const style = INFLUENCE[driver.influence];
            const Icon = style.Icon;
            return (
              <motion.article
                key={`${driver.id}-${driver.title}`}
                className="md:px-7 md:first:pl-0 md:last:pr-0"
                initial={reduce ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, transition: { duration: 0.12 } }}
                transition={{ duration: 0.32, ease: EASE_OUT, delay: i * 0.05 }}
              >
                <span className={`inline-flex h-8 w-8 items-center justify-center rounded-full ring-1 ${style.tone}`}>
                  <motion.span
                    className="inline-flex"
                    initial={reduce ? false : { ...style.from, opacity: 0 }}
                    whileInView={{ ...style.to, opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.55, ease: EASE_OUT, delay: 0.1 + i * 0.08 }}
                  >
                    <Icon className="h-4 w-4" strokeWidth={2.2} aria-hidden="true" />
                  </motion.span>
                </span>
                <h3 className="mt-4 text-[15px] leading-snug font-semibold text-ink">{driver.title}</h3>
                <p className={`mt-1 text-[13px] font-medium ${style.text}`}>{style.label}</p>
                <p className="mt-2 text-[14px] leading-relaxed text-pretty text-muted">{driver.description}</p>
              </motion.article>
            );
          })}
        </AnimatePresence>
      </div>

      <div className="mt-8 border-t border-line pt-4">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="model-signals"
          className="group inline-flex items-center gap-2 rounded-md py-1 text-[14px] font-medium text-ink-soft hover:text-ink"
        >
          {open ? 'Hide model signals' : 'Show model signals'}
          <ChevronDown className={`h-4 w-4 text-faint transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
        </button>

        <AnimatePresence initial={false}>
          {open && (
            <motion.div
              id="model-signals"
              className="overflow-hidden"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: EASE_OUT }}
            >
              <div className="pt-5">
                <ul className="space-y-3.5">
                  {features.map((feature, i) => (
                    <li key={feature.name} className="grid grid-cols-[minmax(0,11rem)_1fr_3rem] items-center gap-4 sm:grid-cols-[14rem_1fr_3rem]">
                      <div className="min-w-0">
                        <div className="truncate text-[14px] text-ink" title={feature.name}>
                          {feature.name}
                        </div>
                        <div className="text-[12px] text-faint">{feature.category}</div>
                      </div>
                      <div className="h-1.5 rounded-full bg-mist" aria-hidden="true">
                        <motion.div
                          className="h-full w-full origin-left rounded-full bg-leaf-600"
                          initial={reduce ? false : { scaleX: 0 }}
                          animate={{ scaleX: feature.weight / maxWeight }}
                          transition={reduce ? { duration: 0 } : { ...DATA_TRANSITION, duration: 0.6, delay: 0.08 + i * 0.06 }}
                        />
                      </div>
                      <div className="data text-right text-[13px] text-ink-soft tabular-nums">{feature.weight}%</div>
                    </li>
                  ))}
                </ul>
                <p className="mt-5 text-[12px] text-muted">
                  Relative contribution of each input to this forecast. Illustrative weights from the demo model.
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}
