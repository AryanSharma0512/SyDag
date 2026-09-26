import { motion, useReducedMotion } from 'motion/react';
import { Hourglass } from 'lucide-react';
import type { ImageryAblation } from '../../types/agricultural';
import { EASE_OUT } from '../../utils/motion';
import { formatDay } from '../../utils/formatters';
import { DataBadge } from '../common/DataBadge';

interface ImageryValueProps {
  ablation: ImageryAblation | null;
  error: string | null;
  season: number;
}

/**
 * Validation error with and without satellite imagery, as the ML team publishes it
 * (GET /api/evaluation/imagery). Until then it says so; it never fills in numbers.
 */
export function ImageryValue({ ablation, error, season }: ImageryValueProps) {
  const reduce = useReducedMotion();
  const ready = ablation?.status === 'ready' && ablation.variants.length > 0;
  const variants = ready ? ablation.variants : [];
  const max = Math.max(1, ...variants.map((v) => v.mae));
  const bestWithout = Math.min(...variants.filter((v) => !v.usesImagery).map((v) => v.mae));
  const bestWith = Math.min(...variants.filter((v) => v.usesImagery).map((v) => v.mae));
  const gain = Number.isFinite(bestWithout) && Number.isFinite(bestWith) ? bestWithout - bestWith : null;

  return (
    <section className="flex h-full min-w-0 flex-col" aria-labelledby="imagery-heading">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="imagery-heading" className="text-[16px] font-semibold tracking-[-0.01em] text-ink">
            What did the satellite imagery add?
          </h2>
          <p className="mt-1 text-[14px] text-muted">
            Validation error of the same model trained on field records alone and with satellite imagery.
          </p>
        </div>
        {ready && ablation.datasetLabel && (
          <DataBadge
            variant={/challenge/i.test(ablation.datasetLabel) ? 'challenge' : 'practice'}
            label={ablation.datasetLabel}
            className="shrink-0"
          />
        )}
      </div>

      {error ? (
        <p className="mt-6 text-[14px] text-muted">The comparison did not load ({error}).</p>
      ) : ablation === null ? (
        <div className="ss-skeleton mt-6 h-[160px] rounded-lg" aria-busy="true" aria-label="Loading comparison" />
      ) : !ready ? (
        <div className="mt-6 flex flex-1 flex-col items-start justify-center gap-3 rounded-xl border border-dashed border-line-strong px-5 py-8">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-mist text-muted">
            <Hourglass className="h-4 w-4" aria-hidden="true" />
          </span>
          <p className="text-[15px] font-medium text-ink">Waiting for the current training run.</p>
          <p className="max-w-sm text-[13px] leading-relaxed text-muted">
            The comparison appears here when the ML team publishes its with and without imagery results.
          </p>
        </div>
      ) : (
        <>
          <p className="mt-3 text-[12px] text-muted">
            MAE, <span className="data">bu/ac</span>
            {ablation.asOf ? ` · forecast date ${formatDay(`${season}-${ablation.asOf}`)}` : ' · full season'}
            {ablation.validation ? ` · ${ablation.validation}` : ''}
          </p>
          <ul className="mt-4 space-y-4">
            {variants.map((v, i) => (
              <li key={v.id}>
                <div className="flex items-baseline justify-between gap-3 text-[14px]">
                  <span className="text-ink">{v.label}</span>
                  <span className="data font-medium text-ink tabular-nums">{v.mae.toFixed(1)}</span>
                </div>
                <div className="mt-1.5 h-2 rounded-full bg-mist" aria-hidden="true">
                  <motion.div
                    className={`h-full w-full origin-left rounded-full ${v.usesImagery ? 'bg-leaf-700' : 'bg-[#B4BAC2]'}`}
                    initial={reduce ? false : { scaleX: 0 }}
                    whileInView={{ scaleX: v.mae / max }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6, ease: EASE_OUT, delay: i * 0.08 }}
                  />
                </div>
              </li>
            ))}
          </ul>
          {gain !== null && (
            <p className="mt-5 border-t border-line pt-3 text-[13px] text-ink-soft">
              Imagery {gain >= 0 ? 'lowered' : 'raised'} validation error by{' '}
              <span className="data font-medium text-ink">{Math.abs(gain).toFixed(1)}</span> bu/ac (
              <span className="data">{Math.round((Math.abs(gain) / bestWithout) * 100)}%</span>).
            </p>
          )}
        </>
      )}
    </section>
  );
}
