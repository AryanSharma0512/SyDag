import { useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ChevronDown, Download } from 'lucide-react';
import type { FieldMeta } from '../../types/agricultural';
import { getLocationContextCsv, type ContextExportType } from '../../services/context';
import { useDismiss } from '../../utils/hooks';
import { EASE_OUT } from '../../utils/motion';
import type { SourceState } from './DataPanel';

interface ExportMenuProps {
  field: FieldMeta;
  dates: string[];
  /** Per-source state from the current response; a source without data can't be exported. */
  states: { weather: SourceState; soil: SourceState; yieldHistory: SourceState };
  /** False until the context response has arrived. */
  ready: boolean;
}

function save(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const UNAVAILABLE: Record<SourceState, string> = {
  ok: '',
  loading: 'Loading',
  unavailable: 'Unavailable',
  not_configured: 'Not configured',
};

export function ExportMenu({ field, dates, states, ready }: ExportMenuProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<ContextExportType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ref = useDismiss<HTMLDivElement>(open, () => setOpen(false));
  const buttonRef = useRef<HTMLButtonElement>(null);

  const items: Array<{ type: ContextExportType; label: string; detail: string; state: SourceState }> = [
    { type: 'weather', label: 'Weather CSV', detail: 'One row per forecast date', state: states.weather },
    { type: 'soil', label: 'Soil CSV', detail: 'Property and value', state: states.soil },
    { type: 'yield-history', label: 'Yield history CSV', detail: 'One row per year', state: states.yieldHistory },
    { type: 'all', label: 'All normalized data', detail: 'Every source and its status', state: ready ? 'ok' : 'loading' },
  ];

  const download = async (type: ContextExportType) => {
    setBusy(type);
    setError(null);
    try {
      const { filename, blob } = await getLocationContextCsv(field, dates, type);
      save(filename, blob);
      setOpen(false);
      buttonRef.current?.focus();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The download failed.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div ref={ref} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="lift inline-flex h-9 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-[13px] font-medium text-ink-soft hover:border-line-strong hover:text-ink"
      >
        <Download className="h-4 w-4" aria-hidden="true" />
        Download data
        <ChevronDown className={`h-4 w-4 text-faint transition-transform duration-200 ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            className="absolute top-full right-0 z-30 mt-2 w-[min(18rem,calc(100vw-2rem))] origin-top-right rounded-xl border border-line bg-surface p-1.5 shadow-lift"
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98, transition: { duration: 0.12 } }}
            transition={{ duration: 0.18, ease: EASE_OUT }}
          >
            <ul role="menu" aria-label="Download data">
              {items.map((item) => {
                const disabled = item.state !== 'ok' || busy !== null;
                return (
                  <li key={item.type} role="none">
                    <button
                      type="button"
                      role="menuitem"
                      disabled={disabled}
                      onClick={() => download(item.type)}
                      className="flex w-full items-start justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-mist/80 focus-visible:bg-mist/80 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                    >
                      <span>
                        <span className={`block text-[14px] font-medium ${item.state === 'ok' ? 'text-ink' : 'text-faint'}`}>{item.label}</span>
                        <span className="mt-0.5 block text-[12px] text-muted">{item.detail}</span>
                      </span>
                      <span className="pt-0.5 text-[12px] whitespace-nowrap text-muted">
                        {busy === item.type ? 'Preparing…' : UNAVAILABLE[item.state]}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <p className="border-t border-line px-3 pt-2.5 pb-1.5 text-[11px] leading-relaxed text-muted">
              Normalized SoilSignal values with source and retrieval time. No raw responses or keys.
            </p>
            {error && (
              <p role="alert" className="px-3 pb-2 text-[12px] text-stress-700">
                {error}
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
