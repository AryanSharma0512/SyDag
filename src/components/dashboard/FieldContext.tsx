import { useRef, useState, type KeyboardEvent } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Check, ChevronDown } from 'lucide-react';
import type { FieldMeta, ForecastSnapshot } from '../../types/agricultural';
import { useDismiss } from '../../utils/hooks';
import { EASE_OUT } from '../../utils/motion';
import { shortCropName } from '../../utils/formatters';

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
  const [open, setOpen] = useState(false);
  const containerRef = useDismiss<HTMLDivElement>(open, () => setOpen(false));
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const focusItem = (i: number) => itemRefs.current[(i + fields.length) % fields.length]?.focus();

  const onMenuKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    const current = itemRefs.current.findIndex((el) => el === document.activeElement);
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      focusItem(current + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      focusItem(current - 1);
    } else if (event.key === 'Home') {
      event.preventDefault();
      focusItem(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      focusItem(fields.length - 1);
    } else if (event.key === 'Tab') {
      setOpen(false);
    }
    event.stopPropagation();
  };

  const choose = (id: string) => {
    setOpen(false);
    buttonRef.current?.focus();
    if (id !== field.id) onSelectField(id);
  };

  return (
    <header className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-1">
        <div ref={containerRef} className="relative">
          <button
            ref={buttonRef}
            type="button"
            aria-haspopup="menu"
            aria-expanded={open}
            aria-label={`Field: ${field.name}. Change field`}
            onClick={() => setOpen((v) => !v)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowDown' && !open) {
                event.preventDefault();
                setOpen(true);
                window.requestAnimationFrame(() => focusItem(fields.findIndex((f) => f.id === field.id)));
              }
            }}
            className="group -mx-2 inline-flex items-center gap-2 rounded-lg px-2 py-1 text-left hover:bg-mist/80"
          >
            <span className="relative inline-grid overflow-hidden">
              <AnimatePresence initial={false} mode="popLayout">
                <motion.span
                  key={field.id}
                  className="text-[22px] font-semibold tracking-[-0.02em] whitespace-nowrap text-ink sm:text-[26px]"
                  {...swap}
                >
                  {field.name}
                </motion.span>
              </AnimatePresence>
            </span>
            <ChevronDown
              className={`h-5 w-5 text-faint transition-transform duration-200 group-hover:text-ink-soft ${open ? 'rotate-180' : ''}`}
            />
          </button>

          <AnimatePresence>
            {open && (
              <motion.ul
                role="menu"
                aria-label="Select a field"
                onKeyDown={onMenuKeyDown}
                className="absolute top-full left-0 z-30 mt-2 w-[min(22rem,calc(100vw-2rem))] origin-top-left rounded-xl border border-line bg-surface p-1.5 shadow-lift"
                initial={{ opacity: 0, y: -4, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -4, scale: 0.98, transition: { duration: 0.12 } }}
                transition={{ duration: 0.18, ease: EASE_OUT }}
              >
                {fields.map((f, i) => {
                  const selected = f.id === field.id;
                  return (
                    <li key={f.id} role="none">
                      <button
                        ref={(el) => {
                          itemRefs.current[i] = el;
                        }}
                        type="button"
                        role="menuitemradio"
                        aria-checked={selected}
                        onClick={() => choose(f.id)}
                        className={`flex w-full items-start justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-mist/80 focus-visible:bg-mist/80 ${
                          selected ? 'bg-leaf-50/70' : ''
                        }`}
                      >
                        <span className="min-w-0">
                          <span className="block text-[14px] font-medium text-ink">{f.name}</span>
                          <span className="mt-0.5 block truncate text-[12px] text-muted">{f.location}</span>
                        </span>
                        <span className="flex shrink-0 items-center gap-2 pt-0.5">
                          <span className="data text-[12px] text-faint">{f.acreage} ac</span>
                          <Check className={`h-4 w-4 text-leaf-700 ${selected ? 'opacity-100' : 'opacity-0'}`} />
                        </span>
                      </button>
                    </li>
                  );
                })}
              </motion.ul>
            )}
          </AnimatePresence>
        </div>

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

      {!isPresentationMode && (
        <p className="text-[14px] text-muted">
          <span className="relative inline-grid overflow-hidden align-bottom">
            <AnimatePresence initial={false} mode="popLayout">
              <motion.span key={snapshot.stage} {...swap}>
                {snapshot.stage} stage
              </motion.span>
            </AnimatePresence>
          </span>
          {' · '}
          {soilLabel ?? field.soilClassification} · Regional baseline <span className="data">{field.regionalBaseline}</span> bu/ac
        </p>
      )}
    </header>
  );
}
