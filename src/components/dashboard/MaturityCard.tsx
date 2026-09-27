import { motion, useReducedMotion } from 'motion/react';
import type { GrowthStage } from '../../types/agricultural';
import type { MaturityEstimate } from '../../types/results';
import { GrowthStageRail } from './GrowthStageRail';
import { formatDay, formatNumber } from '../../utils/formatters';
import { DATA_TRANSITION } from '../../utils/motion';

interface MaturityCardProps {
  /** Growing degree days since planting (°F, base 50) and the date they run to. */
  gdd: { value: number; asOf: string } | null;
  /** Crop stage estimated from GDD by the live model's feature pipeline, when it has one. */
  stage?: GrowthStage;
  stageDetail?: string;
  maturity: MaturityEstimate | null;
  isPresentationMode?: boolean;
}

/**
 * Crop development: heat accumulated since planting and, when the final results
 * publish one, the estimated physiological-maturity window. No date is estimated here.
 */
export function MaturityCard({ gdd, stage, stageDetail, maturity, isPresentationMode = false }: MaturityCardProps) {
  const reduce = useReducedMotion();
  const shown = maturity?.gddSincePlanting != null ? { value: maturity.gddSincePlanting, asOf: maturity.asOf } : gdd;
  const target = maturity?.gddToMaturity ?? null;
  const share = shown && target ? Math.min(1, shown.value / target) : null;
  const big = isPresentationMode ? 'text-[34px]' : 'text-[26px]';
  const text = isPresentationMode ? 'text-[16px]' : 'text-[14px]';

  return (
    <section aria-labelledby="maturity-heading" className="flex h-full flex-col">
      <h2
        id="maturity-heading"
        className={`font-semibold tracking-[-0.015em] text-ink ${isPresentationMode ? 'text-[24px]' : 'text-[19px]'}`}
      >
        Crop development
      </h2>
      <p className={`mt-1 text-muted ${text}`}>Heat accumulated since planting, and when the crop is likely to mature.</p>

      <dl className="mt-5 grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <dt className="text-[13px] text-muted">Accumulated GDD since planting</dt>
          {shown ? (
            <>
              <dd className={`data mt-1 font-medium text-ink ${big}`}>{formatNumber(shown.value)}</dd>
              <dd className="mt-0.5 text-[13px] text-muted">
                as of <span className="data">{formatDay(shown.asOf)}</span> · °F, base 50
              </dd>
            </>
          ) : (
            <dd className="mt-1 text-[14px] text-muted">Published with the final results.</dd>
          )}
        </div>
        <div>
          <dt className="text-[13px] text-muted">Estimated maturity window</dt>
          {maturity?.windowStart && maturity.windowEnd ? (
            <>
              <dd
                className={`data mt-1 font-medium whitespace-nowrap text-ink ${isPresentationMode ? 'text-[28px]' : 'text-[22px]'}`}
              >
                {formatDay(maturity.windowStart)}–{formatDay(maturity.windowEnd)}
              </dd>
              <dd className="mt-0.5 text-[13px] text-muted">Likely physiological maturity</dd>
            </>
          ) : (
            <dd className="mt-1 text-[14px] text-muted">Published with the final results.</dd>
          )}
        </div>
      </dl>

      {share !== null && target && (
        <div className="mt-5">
          <div className="h-2 rounded-full bg-mist" aria-hidden="true">
            <motion.div
              className="h-full origin-left rounded-full bg-sun-500"
              initial={false}
              animate={{ scaleX: share }}
              transition={reduce ? { duration: 0 } : DATA_TRANSITION}
            />
          </div>
          <p className="mt-2 text-[13px] text-muted">
            <span className="data text-ink-soft">{Math.round(share * 100)}%</span> of the{' '}
            <span className="data">{formatNumber(target)}</span> GDD this estimate uses for maturity
          </p>
        </div>
      )}

      {stage && (
        <div className="mt-5 border-t border-line pt-4">
          <GrowthStageRail stage={stage} detail={stageDetail ?? ''} compact={isPresentationMode} />
        </div>
      )}
      {maturity?.method && !isPresentationMode && (
        <p className="mt-3 text-[12px] leading-relaxed text-muted">{maturity.method}</p>
      )}
    </section>
  );
}
