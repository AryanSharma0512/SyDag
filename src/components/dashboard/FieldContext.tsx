import { AnimatePresence, motion } from 'motion/react';
import type { FieldMeta, ForecastSnapshot } from '../../types/agricultural';
import { EASE_OUT } from '../../utils/motion';
import { formatDay, shortCropName } from '../../utils/formatters';
import { FieldSelector } from '../common/FieldSelector';

interface FieldContextProps {
  fields: FieldMeta[];
  field: FieldMeta;
  snapshot: ForecastSnapshot;
  onSelectField: (fieldId: string) => void;
  isPresentationMode?: boolean;
  /** Soil mapped at the field's coordinates, when public data has loaded. */
  soilLabel?: string;
}

const swap = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.15, ease: EASE_OUT },
};

export function FieldContext({ fields, field, snapshot, onSelectField, isPresentationMode = false, soilLabel }: FieldContextProps) {
  // The trial record first: what was planted, how it was managed, where.
  const identity = [
    field.hybrid && { label: 'Hybrid', value: field.hybrid },
    field.nitrogenLbAc != null && { label: 'N rate', value: `${Math.round(field.nitrogenLbAc)} lb/ac` },
    { label: 'Water', value: field.irrigationStatus },
    field.site && { label: 'Site', value: field.site },
    field.plantingDate && { label: 'Planted', value: formatDay(field.plantingDate) },
  ].filter(Boolean) as Array<{ label: string; value: string }>;

  return (
    <header className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-1">
        <FieldSelector fields={fields} field={field} onSelectField={onSelectField} />

        <span className="text-[16px] text-muted">
          {shortCropName(field.crop)} · <span className="data">{field.season}</span>
        </span>

        <span className="relative inline-grid overflow-hidden" aria-live="polite">
          <span className="sr-only">Forecast date </span>
          <AnimatePresence initial={false} mode="popLayout">
            <motion.span key={snapshot.id} className="data text-[16px] font-medium text-ink" {...swap}>
              {snapshot.displayDate}
            </motion.span>
          </AnimatePresence>
        </span>
      </div>

      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-[14px]">
        {identity.map((item) => (
          <div key={item.label} className="flex items-baseline gap-1.5">
            <dt className="text-muted">{item.label}</dt>
            <dd className={`font-medium text-ink ${item.label === 'Hybrid' || item.label === 'N rate' ? 'data' : ''}`}>{item.value}</dd>
          </div>
        ))}
      </dl>

      {!isPresentationMode && (
        <p className="text-[13px] text-muted">
          <span className="relative inline-grid overflow-hidden align-bottom">
            <AnimatePresence initial={false} mode="popLayout">
              <motion.span key={snapshot.stage} {...swap}>
                {snapshot.stage} stage
              </motion.span>
            </AnimatePresence>
          </span>
          {' · '}
          {soilLabel ?? field.soilClassification} · County 5-yr average <span className="data">{field.regionalBaseline}</span> bu/ac
        </p>
      )}
    </header>
  );
}
