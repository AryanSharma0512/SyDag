import { useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'motion/react';
import { RotateCcw, Wrench, X } from 'lucide-react';
import type { FieldMeta } from '../../types/agricultural';
import { useDismiss } from '../../utils/hooks';
import { EASE_OUT } from '../../utils/motion';

interface DebugPanelProps {
  fields: FieldMeta[];
  selectedFieldId: string;
  onSelectField: (fieldId: string) => void;
  simulateLoading: boolean;
  onToggleLoading: () => void;
  simulateMissingSatellite: boolean;
  onToggleMissingSatellite: () => void;
  simulateWeatherError: boolean;
  onToggleWeatherError: () => void;
  onReset: () => void;
  isPresentationMode: boolean;
  onTogglePresentationMode: () => void;
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      className="flex w-full items-center justify-between rounded-lg px-2 py-2 text-left text-[13px] text-ink-soft hover:bg-mist/70"
    >
      {label}
      <span className={`relative h-[18px] w-8 rounded-full transition-colors duration-200 ${checked ? 'bg-leaf-700' : 'bg-line-strong'}`}>
        <motion.span
          className="absolute top-[2px] left-[2px] h-[14px] w-[14px] rounded-full bg-surface shadow-sm"
          initial={false}
          animate={{ x: checked ? 14 : 0 }}
          transition={{ type: 'spring', stiffness: 500, damping: 34 }}
        />
      </span>
    </button>
  );
}

/**
 * Diagnostics for demos and QA. Only rendered with ?debug=true, as a small
 * floating control instead of a permanent ribbon.
 */
export function DebugPanel(props: DebugPanelProps) {
  const [open, setOpen] = useState(false);
  const ref = useDismiss<HTMLDivElement>(open, () => setOpen(false));

  return createPortal(
    <div ref={ref} className="fixed right-4 bottom-4 z-50 flex flex-col items-end gap-3 sm:right-6 sm:bottom-6">
      <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-label="Diagnostics"
            className="w-[19rem] origin-bottom-right rounded-2xl border border-line bg-surface p-3 shadow-lift"
            initial={{ opacity: 0, y: 8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.97, transition: { duration: 0.12 } }}
            transition={{ duration: 0.2, ease: EASE_OUT }}
          >
            <div className="flex items-center justify-between px-2 pt-1 pb-2">
              <span className="text-[13px] font-semibold text-ink">Diagnostics</span>
              <span className="data text-[11px] text-faint">?debug=true</span>
            </div>

            <div className="border-t border-line px-2 pt-3 pb-2">
              <div className="text-[12px] text-muted">Scenario</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {props.fields.map((f, i) => {
                  const active = f.id === props.selectedFieldId;
                  return (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => props.onSelectField(f.id)}
                      aria-pressed={active}
                      title={`Shortcut: ${i + 1}`}
                      className={`rounded-full border px-2.5 py-1 text-[12px] transition-colors ${
                        active ? 'border-leaf-700 bg-leaf-700 text-white' : 'border-line text-ink-soft hover:border-line-strong'
                      }`}
                    >
                      {f.name.replace(' Plot ', ' ').replace(' Field ', ' ')}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mt-1 border-t border-line pt-1">
              <Toggle label="Loading state" checked={props.simulateLoading} onChange={props.onToggleLoading} />
              <Toggle label="Satellite missing" checked={props.simulateMissingSatellite} onChange={props.onToggleMissingSatellite} />
              <Toggle label="Weather error" checked={props.simulateWeatherError} onChange={props.onToggleWeatherError} />
              <Toggle label="Presentation mode" checked={props.isPresentationMode} onChange={props.onTogglePresentationMode} />
            </div>

            <div className="mt-1 flex items-center justify-between border-t border-line px-2 pt-3 pb-1">
              <span className="data text-[11px] leading-relaxed text-faint">← → dates · 1–5 fields · R reset · F present</span>
              <button
                type="button"
                onClick={props.onReset}
                className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[12px] text-ink-soft hover:border-line-strong hover:text-ink"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                Reset
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? 'Close diagnostics' : 'Open diagnostics'}
        className="lift flex h-11 w-11 items-center justify-center rounded-full border border-line bg-surface text-ink-soft shadow-float hover:text-ink hover:shadow-lift"
      >
        {open ? <X className="h-4.5 w-4.5" /> : <Wrench className="h-4.5 w-4.5" />}
      </button>
    </div>,
    document.body,
  );
}
