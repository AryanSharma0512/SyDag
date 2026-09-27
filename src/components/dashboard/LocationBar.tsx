import { useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Check, ChevronDown, Search } from 'lucide-react';
import type { TrialSite } from '../../types/sites';
import type { PlotOption } from '../../services/plotForecasts';
import { hasForecasts } from '../../services/sites';
import { useDismiss } from '../../utils/hooks';
import { EASE_OUT } from '../../utils/motion';
import { SegmentedControl } from '../common/SegmentedControl';

interface LocationTabsProps {
  sites: TrialSite[];
  selectedId: string;
  onSelect: (siteId: string) => void;
  large?: boolean;
}

/** Location first: one tab per trial site. Sites without forecasts stay selectable but quiet. */
export function LocationTabs({ sites, selectedId, onSelect, large = false }: LocationTabsProps) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const i = sites.findIndex((s) => s.id === selectedId);
    let next = i;
    if (event.key === 'ArrowRight') next = (i + 1) % sites.length;
    else if (event.key === 'ArrowLeft') next = (i - 1 + sites.length) % sites.length;
    else return;
    event.preventDefault();
    event.stopPropagation();
    onSelect(sites[next].id);
    refs.current[next]?.focus();
  };

  return (
    <div role="tablist" aria-label="Trial location" onKeyDown={onKeyDown} className="-mx-1 flex flex-wrap gap-1.5">
      {sites.map((site, i) => {
        const active = site.id === selectedId;
        const available = hasForecasts(site);
        return (
          <button
            key={site.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onSelect(site.id)}
            title={available ? undefined : 'No plot forecasts for this location yet'}
            className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 font-medium transition-colors duration-150 ${
              large ? 'text-[16px]' : 'text-[14px]'
            } ${
              active
                ? 'border-ink bg-ink text-white'
                : available
                  ? 'border-line-strong bg-surface text-ink hover:border-faint'
                  : 'border-line bg-transparent text-muted hover:border-line-strong hover:text-ink-soft'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${available ? (active ? 'bg-leaf-300' : 'bg-leaf-600') : active ? 'border border-white/60' : 'border border-faint'}`}
              aria-hidden="true"
            />
            {site.name}
            {site.state && <span className={active ? 'text-white/60' : 'text-faint'}>{site.state}</span>}
          </button>
        );
      })}
    </div>
  );
}

interface SeasonPickerProps {
  seasons: number[];
  value: number;
  onChange: (season: number) => void;
}

/** Hidden when there is only one season to show. */
export function SeasonPicker({ seasons, value, onChange }: SeasonPickerProps) {
  if (seasons.length < 2) return null;
  return (
    <SegmentedControl
      ariaLabel="Season"
      size="sm"
      mono
      options={seasons.map((s) => ({ value: String(s), label: String(s) }))}
      value={String(value)}
      onChange={(v) => onChange(Number(v))}
    />
  );
}

interface PlotPickerProps {
  plots: PlotOption[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

const SEARCH_FROM = 10;

/** The plots at one site, as a compact menu with a filter when the list is long. */
export function PlotPicker({ plots, selectedKey, onSelect }: PlotPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const containerRef = useDismiss<HTMLDivElement>(open, () => setOpen(false));
  const buttonRef = useRef<HTMLButtonElement>(null);
  const selected = plots.find((p) => p.key === selectedKey) ?? null;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return plots;
    return plots.filter((p) => `${p.label} ${p.detail}`.toLowerCase().includes(q));
  }, [plots, query]);
  const featuredCount = filtered.filter((p) => p.featured).length;
  const showGroups = featuredCount > 0 && featuredCount < filtered.length;
  // The final results feature one plot per site, chosen by a fixed rule (see its detail line).
  const featuredHeading = filtered.some((p) => p.featured && p.source === 'live') ? 'Featured plots' : 'Representative plot';

  const choose = (key: string) => {
    setOpen(false);
    setQuery('');
    buttonRef.current?.focus();
    if (key !== selectedKey) onSelect(key);
  };

  if (plots.length === 0) return null;

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Plot: ${selected?.label ?? 'none'}. Change plot (${plots.length} at this location)`}
        onClick={() => setOpen((v) => !v)}
        className="group -mx-2 inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-left hover:bg-mist/80"
      >
        <span className="font-medium whitespace-nowrap text-ink">{selected?.label ?? 'Choose a plot'}</span>
        <ChevronDown
          className={`h-4 w-4 text-faint transition-transform duration-200 group-hover:text-ink-soft ${open ? 'rotate-180' : ''}`}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            className="absolute top-full left-0 z-30 mt-2 w-[min(24rem,calc(100vw-2rem))] origin-top-left rounded-xl border border-line bg-surface p-1.5 shadow-lift"
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98, transition: { duration: 0.12 } }}
            transition={{ duration: 0.18, ease: EASE_OUT }}
          >
            {plots.length >= SEARCH_FROM && (
              <label className="flex items-center gap-2 border-b border-line px-2.5 pt-1 pb-2">
                <Search className="h-4 w-4 text-faint" aria-hidden="true" />
                <input
                  autoFocus
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={`Filter ${plots.length} plots by id${plots.some((p) => p.source === 'live' || p.resultPlot?.hybrid) ? ' or hybrid' : ''}`}
                  aria-label="Filter plots"
                  className="w-full bg-transparent py-1 text-[14px] text-ink outline-none placeholder:text-faint"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && filtered[0]) choose(filtered[0].key);
                  }}
                />
              </label>
            )}
            <ul role="listbox" aria-label="Plots" className="max-h-[min(22rem,60vh)] overflow-y-auto pt-1">
              {filtered.map((p, i) => {
                const active = p.key === selectedKey;
                return (
                  <li key={p.key} role="none">
                    {showGroups && (i === 0 || i === featuredCount) && (
                      <p className="px-3 pt-2 pb-1 text-[11px] font-medium tracking-[0.06em] text-faint uppercase">
                        {i === 0 ? featuredHeading : 'All plots'}
                      </p>
                    )}
                    <button
                      type="button"
                      role="option"
                      aria-selected={active}
                      onClick={() => choose(p.key)}
                      className={`flex w-full items-start justify-between gap-3 rounded-lg px-3 py-2 text-left transition-colors hover:bg-mist/80 focus-visible:bg-mist/80 ${
                        active ? 'bg-leaf-50/70' : ''
                      }`}
                    >
                      <span className="min-w-0">
                        <span className="data block text-[14px] text-ink">{p.label}</span>
                        {p.detail && <span className="mt-0.5 block truncate text-[12px] text-muted">{p.detail}</span>}
                      </span>
                      <Check className={`mt-0.5 h-4 w-4 shrink-0 text-leaf-700 ${active ? 'opacity-100' : 'opacity-0'}`} />
                    </button>
                  </li>
                );
              })}
              {filtered.length === 0 && <li className="px-3 py-3 text-[13px] text-muted">No plot matches “{query}”.</li>}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
