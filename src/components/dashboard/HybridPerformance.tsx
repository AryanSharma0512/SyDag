import { useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { PlotDecision } from '../../types/agricultural';
import { SegmentedControl } from '../common/SegmentedControl';
import { formatYield } from '../../utils/formatters';

type SortKey = 'yield' | 'consistent' | 'uncertain';

const SORTS: Array<{ value: SortKey; label: string }> = [
  { value: 'yield', label: 'Highest predicted yield' },
  { value: 'consistent', label: 'Most consistent' },
  { value: 'uncertain', label: 'Most uncertain' },
];

/** A hybrid is summarized only with this many plots; the section needs this many such hybrids. */
export const MIN_PLOTS_PER_HYBRID = 3;
export const MIN_HYBRIDS = 3;
const DEFAULT_ROWS = 10;

interface HybridRow {
  hybrid: string;
  plots: number;
  meanYield: number;
  spread: number; // standard deviation of the plot forecasts
  halfRange: number; // mean half-width of the 90% range
  sites: number;
}

const mean = (values: number[]) => values.reduce((a, b) => a + b, 0) / values.length;

export function summarizeHybrids(plots: PlotDecision[]): HybridRow[] {
  const groups = new Map<string, PlotDecision[]>();
  for (const p of plots) if (p.hybrid) groups.set(p.hybrid, [...(groups.get(p.hybrid) ?? []), p]);
  return [...groups.entries()]
    .filter(([, group]) => group.length >= MIN_PLOTS_PER_HYBRID)
    .map(([hybrid, group]) => {
      const yields = group.map((p) => p.predictedYield);
      const m = mean(yields);
      return {
        hybrid,
        plots: group.length,
        meanYield: m,
        spread: Math.sqrt(mean(yields.map((y) => (y - m) ** 2))),
        halfRange: mean(group.map((p) => (p.upperBound - p.lowerBound) / 2)),
        sites: new Set(group.map((p) => p.site ?? '')).size,
      };
    });
}

const ORDER: Record<SortKey, (a: HybridRow, b: HybridRow) => number> = {
  yield: (a, b) => b.meanYield - a.meanYield,
  consistent: (a, b) => a.spread - b.spread,
  uncertain: (a, b) => b.halfRange - a.halfRange,
};

/**
 * Which hybrids are on track, from the same plot forecasts as the scouting queue.
 * Renders nothing when too few hybrids have enough plots to compare fairly.
 */
export function HybridPerformance({ plots, asOfLabel }: { plots: PlotDecision[]; asOfLabel: string }) {
  const [sort, setSort] = useState<SortKey>('yield');
  const [showAll, setShowAll] = useState(false);
  const rows = useMemo(() => summarizeHybrids(plots), [plots]);
  const sorted = useMemo(() => [...rows].sort((a, b) => ORDER[sort](a, b) || a.hybrid.localeCompare(b.hybrid)), [rows, sort]);
  if (rows.length < MIN_HYBRIDS) return null;

  return (
    <section aria-labelledby="hybrids-heading">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 id="hybrids-heading" className="text-[20px] font-semibold tracking-[-0.02em] text-ink">
            Hybrid performance
          </h2>
          <p className="mt-1.5 max-w-2xl text-[14px] text-pretty text-muted">
            Mean forecast per hybrid as of {asOfLabel}, for hybrids with at least {MIN_PLOTS_PER_HYBRID} plots.
          </p>
        </div>
        <div className="overflow-x-auto">
          <SegmentedControl ariaLabel="Sort hybrids" size="sm" value={sort} onChange={setSort} options={SORTS} />
        </div>
      </div>

      <div className="mt-4 overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[560px] text-left text-[13px]">
          <caption className="sr-only">Hybrids sorted by {SORTS.find((s) => s.value === sort)?.label.toLowerCase()}</caption>
          <thead className="bg-mist/60 text-[11px] font-medium tracking-wide text-muted uppercase">
            <tr>
              <th scope="col" className="py-2.5 pr-2 pl-4 font-medium">Hybrid</th>
              <th scope="col" className="px-2 py-2.5 text-right font-medium">Plots</th>
              <th scope="col" className={`px-2 py-2.5 text-right font-medium ${sort === 'yield' ? 'text-ink' : ''}`}>
                Predicted yield
              </th>
              <th scope="col" className={`px-2 py-2.5 text-right font-medium ${sort === 'consistent' ? 'text-ink' : ''}`} title="Standard deviation of the plot forecasts, bu/ac">
                Plot spread
              </th>
              <th scope="col" className={`px-2 py-2.5 text-right font-medium ${sort === 'uncertain' ? 'text-ink' : ''}`} title="Mean half-width of the 90% range, bu/ac">
                Typical range
              </th>
              <th scope="col" className="py-2.5 pr-4 pl-2 text-right font-medium">Sites</th>
            </tr>
          </thead>
          <tbody>
            {(showAll ? sorted : sorted.slice(0, DEFAULT_ROWS)).map((row) => (
              <tr key={row.hybrid} className="h-11 border-t border-line">
                <td className="max-w-[16rem] truncate py-2 pr-2 pl-4 font-medium text-ink" title={row.hybrid}>
                  {row.hybrid}
                </td>
                <td className="data px-2 text-right text-ink-soft tabular-nums">{row.plots}</td>
                <td className="data px-2 text-right font-medium text-ink tabular-nums">{formatYield(row.meanYield)}</td>
                <td className="data px-2 text-right text-ink-soft tabular-nums">±{row.spread.toFixed(1)}</td>
                <td className="data px-2 text-right text-ink-soft tabular-nums">±{Math.round(row.halfRange)}</td>
                <td className="data py-2 pr-4 pl-2 text-right text-ink-soft tabular-nums">{row.sites}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sorted.length > DEFAULT_ROWS && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          aria-expanded={showAll}
          className="mt-3 inline-flex items-center gap-1.5 rounded-md py-1 text-[14px] font-medium text-ink-soft hover:text-ink"
        >
          {showAll ? `Show top ${DEFAULT_ROWS}` : `View all ${sorted.length} hybrids`}
          <ChevronDown className={`h-4 w-4 text-faint transition-transform duration-200 ${showAll ? 'rotate-180' : ''}`} />
        </button>
      )}
      <p className="mt-3 text-[12px] text-muted">
        Predicted yield and typical range are means over each hybrid's plots, in bu/ac. Plot spread is how much those plot
        forecasts differ from each other.
      </p>
    </section>
  );
}
