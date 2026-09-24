import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import type { GrowthStage } from '../../types/agricultural';
import { useElementWidth } from '../../utils/hooks';
import { DATA_TRANSITION, GLIDE } from '../../utils/motion';

export const GROWTH_STAGES: GrowthStage[] = ['Emergence', 'Vegetative', 'Reproductive', 'Grain Fill', 'Maturity'];

interface GrowthStageRailProps {
  stage: GrowthStage;
  detail: string;
  compact?: boolean;
}

/** A quiet progression rail. The selected date's stage is highlighted and the indicator glides between stages. */
export function GrowthStageRail({ stage, detail, compact = false }: GrowthStageRailProps) {
  const reduce = useReducedMotion();
  const [railRef, railWidth] = useElementWidth<HTMLDivElement>();
  const current = Math.max(0, GROWTH_STAGES.indexOf(stage));
  const step = GROWTH_STAGES.length > 1 ? railWidth / (GROWTH_STAGES.length - 1) : 0;
  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-[13px] font-medium text-ink-soft">Growth stage</span>
        {!compact && (
          <div className="relative hidden min-w-0 flex-1 justify-end overflow-hidden sm:flex">
            <AnimatePresence initial={false} mode="wait">
              <motion.span
                key={detail}
                className="truncate text-[13px] text-muted"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.18 }}
              >
                {detail}
              </motion.span>
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* Rail: dots sit at the center of five equal columns so they align with the labels. */}
      <div className="relative mt-4 px-[10%]">
        <div ref={railRef} className="relative h-4">
          <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-line-strong" />
          <motion.div
            className="absolute top-1/2 left-0 h-[2px] w-full origin-left -translate-y-1/2 rounded-full bg-leaf-700"
            initial={false}
            animate={{ scaleX: current / (GROWTH_STAGES.length - 1) }}
            transition={transition}
          />
          {GROWTH_STAGES.map((s, i) => (
            <motion.span
              key={s}
              className="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px]"
              style={{ left: `${(i / (GROWTH_STAGES.length - 1)) * 100}%` }}
              initial={false}
              animate={{
                backgroundColor: i <= current ? '#086C4C' : '#FFFFFF',
                borderColor: i <= current ? '#086C4C' : '#D6D2C8',
              }}
              transition={transition}
            />
          ))}
          {railWidth > 0 && (
            <motion.span
              className="absolute top-1/2 left-0 -mt-[9px] -ml-[9px] h-[18px] w-[18px] rounded-full bg-leaf-700/15"
              initial={false}
              animate={{ x: current * step }}
              transition={reduce ? { duration: 0 } : GLIDE}
              aria-hidden="true"
            >
              <span className="absolute inset-[4px] rounded-full border-2 border-surface bg-leaf-700 shadow-[0_1px_3px_rgb(20_32_43/0.25)]" />
            </motion.span>
          )}
        </div>
      </div>

      <ol className="mt-2.5 grid grid-cols-5 text-center" aria-label="Growth stages">
        {GROWTH_STAGES.map((s, i) => {
          const isCurrent = i === current;
          return (
            <li
              key={s}
              aria-current={isCurrent ? 'step' : undefined}
              className={`text-[12px] leading-tight transition-colors duration-300 sm:text-[13px] ${
                isCurrent ? 'font-medium text-ink' : i < current ? 'text-ink-soft' : 'text-faint'
              } ${isCurrent ? '' : 'max-sm:invisible'}`}
            >
              {s}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
