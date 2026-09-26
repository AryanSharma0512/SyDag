import { useMemo, useState, type ReactNode } from 'react';
import { ChevronDown, RefreshCw } from 'lucide-react';
import type { DecisionSet, PlotDecision } from '../../types/agricultural';
import { SegmentedControl } from '../common/SegmentedControl';
import { formatDay, formatYield } from '../../utils/formatters';
import { formatFullDay } from '../../utils/imagery';

type SortKey = 'uncertain' | 'lowest' | 'highest' | 'change';

const SORTS: Array<{ value: SortKey; label: string }> = [
  { value: 'uncertain', label: 'Most uncertain' },
  { value: 'lowest', label: 'Lowest forecast' },
  { value: 'highest', label: 'Highest forecast' },
  { value: 'change', label: 'Largest change' },
];

const DEFAULT_ROWS = 10;

const width = (p: PlotDecision) => p.upperBound - p.lowerBound;
const tenths = (v: number) => Math.round(v * 10);
export const plotLabel = (p: { plotId?: string; name: string }) => p.plotId ?? p.name;

/** Transparent orderings only: every key is a number shown in the table. */
const ORDER: Record<SortKey, (a: PlotDecision, b: PlotDecision) => number> = {
  uncertain: (a, b) =>
    tenths(width(b)) - tenths(width(a)) || a.confidence - b.confidence || a.predictedYield - b.predictedYield,
  lowest: (a, b) => a.predictedYield - b.predictedYield,
  highest: (a, b) => b.predictedYield - a.predictedYield,
  change: (a, b) => Math.abs(b.changeSincePrevious ?? -1) - Math.abs(a.changeSincePrevious ?? -1),
};

interface ScoutingQueueProps {
  decisions: DecisionSet | null;
  /** A newer date is loading; the rows shown are still for `decisions.asOfDate`. */
  updating: boolean;
  error: string | null;
  onRetry: () => void;
  selectedFieldId: string;
  onSelectPlot: (fieldId: string) => void;
}

export function ScoutingQueue({ decisions, updating, error, onRetry, selectedFieldId, onSelectPlot }: ScoutingQueueProps) {
  const [sort, setSort] = useState<SortKey>('uncertain');
  const [showAll, setShowAll] = useState(false);
  const plots = decisions?.plots ?? [];

  const sorted = useMemo(
    () => [...plots].sort((a, b) => ORDER[sort](a, b) || plotLabel(a).localeCompare(plotLabel(b))),
    [plots, sort],
  );
  const rows = showAll ? sorted : sorted.slice(0, DEFAULT_ROWS);

  const widths = plots.map(width);
  const sameWidth = plots.length > 1 && Math.max(...widths) - Math.min(...widths) < 1;
  const previousDate = plots.find((p) => p.previousForecastDate)?.previousForecastDate;
  const distinct = (values: Array<string | undefined>) => [...new Set(values.filter(Boolean))] as string[];
  const sites = distinct(plots.map((p) => p.site));
  const irrigation = distinct(plots.map((p) => p.irrigationStatus));
  const showSite = sites.length > 1;
  const showIrrigation = irrigation.length > 1;

  // Shared scale for the range glyphs, so ranges compare down the column.
  const lo = Math.min(...plots.map((p) => p.lowerBound));
  const hi = Math.max(...plots.map((p) => p.upperBound));
  const span = Math.max(1, hi - lo);

  const sortNote = {
    uncertain: sameWidth
      ? 'Every plot has the same 90% range width on this date, so ties go to lower confidence, then lower forecast.'
      : 'Widest 90% range first.',
    lowest: 'Lowest predicted yield first.',
    highest: 'Highest predicted yield first.',
    change: previousDate
      ? `Largest revision since the ${formatDay(previousDate)} forecast, up or down.`
      : 'This is the first forecast date, so there is no earlier forecast to compare with.',
  }[sort];

  const summary = decisions
    ? [
        `${plots.length} ${plots.length === 1 ? 'plot' : 'plots'}`,
        !showSite && sites[0],
        !showIrrigation && irrigation[0],
        `data through ${formatFullDay(decisions.asOfDate)}`,
      ]
        .filter(Boolean)
        .join(' · ')
    : null;

  return (
    <section aria-labelledby="queue-heading">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 id="queue-heading" className="text-[20px] font-semibold tracking-[-0.02em] text-ink">
            Plots to review
          </h2>
          <p className="mt-1.5 max-w-2xl text-[14px] text-pretty text-muted">
            Sort the trial by uncertainty or predicted yield to decide where a scouting visit may be most useful.
          </p>
        </div>
        <div className="hidden shrink-0 sm:block">
          <SegmentedControl ariaLabel="Sort plots" size="sm" value={sort} onChange={setSort} options={SORTS} />
        </div>
        <label className="flex items-center gap-2 text-[13px] text-muted sm:hidden">
          Sort
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as SortKey)}
            className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[14px] text-ink"
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-3 flex flex-col gap-1 text-[12px] leading-relaxed text-muted sm:flex-row sm:justify-between sm:gap-6">
        <span aria-live="polite">
          {summary}
          {updating && <span className="text-faint"> · updating…</span>}
        </span>
        <span className="sm:text-right">{sortNote}</span>
      </div>

      {error && !decisions ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-sun-300/70 bg-surface px-4 py-3 text-[14px] text-muted">
          <span>The plot list did not load ({error}).</span>
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 font-medium text-ink-soft hover:bg-mist hover:text-ink"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Retry
          </button>
        </div>
      ) : !decisions ? (
        <div className="mt-4 space-y-2" aria-busy="true" aria-label="Loading plots">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="ss-skeleton h-10 rounded-lg" />
          ))}
        </div>
      ) : (
        <div className={`transition-opacity duration-200 ${updating ? 'opacity-60' : ''}`}>
          {/* Tablet and desktop: a dense, scannable table. */}
          <div className="mt-4 hidden overflow-hidden rounded-xl border border-line md:block">
            <table className="w-full table-fixed text-left text-[13px]">
              <caption className="sr-only">
                Plots sorted by {SORTS.find((s) => s.value === sort)?.label.toLowerCase()}. Select a plot to open it below.
              </caption>
              <colgroup>
                <col className="w-[7.5rem]" />
                <col />
                {showSite && <col className="w-[8rem]" />}
                {showIrrigation && <col className="w-[6.5rem]" />}
                <col className="w-[4.5rem]" />
                <col className="w-[5.5rem]" />
                <col className="w-[7.5rem] lg:w-[12.5rem]" />
                <col className="w-[4.5rem]" />
                <col className="w-[6rem] lg:w-[5.5rem]" />
              </colgroup>
              <thead className="bg-mist/60 text-[11px] font-medium tracking-wide text-muted uppercase">
                <tr>
                  <Th>Plot</Th>
                  <Th>Hybrid</Th>
                  {showSite && <Th>Site</Th>}
                  {showIrrigation && <Th>Water</Th>}
                  <Th right title="Nitrogen rate, lb/ac">
                    N rate
                  </Th>
                  <Th right active={sort === 'lowest' || sort === 'highest'} title="Predicted yield, bu/ac">
                    Forecast
                  </Th>
                  <Th right active={sort === 'uncertain'} title="90% prediction range, bu/ac">
                    90% range
                  </Th>
                  <Th right title="Confidence">
                    Conf.
                  </Th>
                  <Th right active={sort === 'change'} className="pr-4 lg:pr-2" title="Change since the previous forecast date, bu/ac">
                    Δ prev.
                  </Th>
                  <Th className="hidden lg:table-cell" title="The input that pushed this estimate down the most">
                    Pushed down most
                  </Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const selected = p.fieldId === selectedFieldId;
                  return (
                    <tr
                      key={p.fieldId}
                      onClick={() => onSelectPlot(p.fieldId)}
                      className={`h-12 cursor-pointer border-t border-line transition-colors duration-150 ${
                        selected ? 'bg-leaf-50/80' : 'hover:bg-mist/50'
                      }`}
                    >
                      <td className="py-2 pr-2 pl-4">
                        <button
                          type="button"
                          aria-current={selected ? 'true' : undefined}
                          aria-label={`Open ${p.name}`}
                          className="data flex items-center gap-2 rounded text-left font-medium text-ink"
                        >
                          <span
                            className={`h-1.5 w-1.5 shrink-0 rounded-full ${selected ? 'bg-leaf-700' : 'bg-transparent'}`}
                            aria-hidden="true"
                          />
                          <span className="truncate">{plotLabel(p)}</span>
                        </button>
                      </td>
                      <td className="truncate px-2 text-ink-soft" title={p.hybrid}>
                        {p.hybrid ?? <Missing />}
                      </td>
                      {showSite && <td className="truncate px-2 text-ink-soft">{p.site ?? <Missing />}</td>}
                      {showIrrigation && <td className="truncate px-2 text-ink-soft">{p.irrigationStatus}</td>}
                      <td className="data px-2 text-right text-ink-soft tabular-nums">
                        {p.nitrogenLbAc != null ? Math.round(p.nitrogenLbAc) : <Missing />}
                      </td>
                      <td className="data px-2 text-right font-medium text-ink tabular-nums">{formatYield(p.predictedYield)}</td>
                      <td className="px-2">
                        <div className="flex items-center justify-end gap-3">
                          <span className="data text-ink-soft tabular-nums">
                            {Math.round(p.lowerBound)}–{Math.round(p.upperBound)}
                          </span>
                          <RangeGlyph
                            start={(p.lowerBound - lo) / span}
                            end={(p.upperBound - lo) / span}
                            point={(p.predictedYield - lo) / span}
                          />
                        </div>
                      </td>
                      <td className="data px-2 text-right text-ink-soft tabular-nums">{Math.round(p.confidence)}%</td>
                      <td className="pr-4 pl-2 text-right lg:pr-2">
                        <Change value={p.changeSincePrevious} />
                      </td>
                      <td className="hidden truncate py-2 pr-4 pl-4 text-muted lg:table-cell" title={p.topNegativeDriver ?? undefined}>
                        {p.topNegativeDriver ?? <Missing />}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Phones: one compact stacked row per plot. */}
          <ul className="mt-4 divide-y divide-line border-y border-line md:hidden">
            {rows.map((p) => {
              const selected = p.fieldId === selectedFieldId;
              return (
                <li key={p.fieldId}>
                  <button
                    type="button"
                    onClick={() => onSelectPlot(p.fieldId)}
                    aria-current={selected ? 'true' : undefined}
                    className={`w-full px-1 py-3 text-left transition-colors ${selected ? 'bg-leaf-50/80' : 'active:bg-mist/60'}`}
                  >
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="data flex min-w-0 items-center gap-2 text-[14px] font-medium text-ink">
                        {selected && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-leaf-700" aria-hidden="true" />}
                        <span className="truncate">{plotLabel(p)}</span>
                      </span>
                      <span className="shrink-0 whitespace-nowrap">
                        <span className="data text-[15px] font-medium text-ink tabular-nums">{formatYield(p.predictedYield)}</span>
                        <span className="data ml-1 text-[11px] text-muted">bu/ac</span>
                      </span>
                    </span>
                    <span className="mt-1 flex items-baseline justify-between gap-3 text-[13px] text-muted">
                      <span className="min-w-0 truncate">
                        {[p.hybrid, p.nitrogenLbAc != null ? `${Math.round(p.nitrogenLbAc)} lb N` : null, showSite ? p.site : null]
                          .filter(Boolean)
                          .join(' · ') || p.irrigationStatus}
                      </span>
                      <span className="data shrink-0 tabular-nums">
                        {Math.round(p.lowerBound)}–{Math.round(p.upperBound)} · {Math.round(p.confidence)}%
                      </span>
                    </span>
                    {p.changeSincePrevious != null && p.previousForecastDate && (
                      <span className="mt-0.5 block text-[12px] text-muted">
                        <Change value={p.changeSincePrevious} /> since {formatDay(p.previousForecastDate)}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>

          {sorted.length > DEFAULT_ROWS && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              aria-expanded={showAll}
              className="mt-3 inline-flex items-center gap-1.5 rounded-md py-1 text-[14px] font-medium text-ink-soft hover:text-ink"
            >
              {showAll ? `Show top ${DEFAULT_ROWS}` : `View all ${sorted.length} plots`}
              <ChevronDown className={`h-4 w-4 text-faint transition-transform duration-200 ${showAll ? 'rotate-180' : ''}`} />
            </button>
          )}
        </div>
      )}
    </section>
  );
}

function Th({
  children,
  right = false,
  active = false,
  className = '',
  title,
}: {
  children: ReactNode;
  right?: boolean;
  active?: boolean;
  className?: string;
  title?: string;
}) {
  return (
    <th
      scope="col"
      title={title}
      aria-sort={active ? 'other' : undefined}
      className={`px-2 py-2.5 font-medium whitespace-nowrap first:pl-4 last:pr-4 ${right ? 'text-right' : ''} ${
        active ? 'text-ink' : ''
      } ${className}`}
    >
      {children}
    </th>
  );
}

function Missing() {
  return (
    <span className="text-faint" aria-label="not recorded">
      —
    </span>
  );
}

function Change({ value }: { value: number | null | undefined }) {
  if (value == null) return <Missing />;
  const tone = value <= -5 ? 'text-stress-600' : value >= 5 ? 'text-leaf-700' : 'text-ink-soft';
  const sign = value > 0 ? '+' : value < 0 ? '−' : '±';
  return <span className={`data tabular-nums ${tone}`}>{`${sign}${Math.abs(value).toFixed(1)}`}</span>;
}

/** The 90% range on the table's shared scale, with a tick at the forecast. */
function RangeGlyph({ start, end, point }: { start: number; end: number; point: number }) {
  return (
    <span className="relative hidden h-1.5 w-16 shrink-0 rounded-full bg-mist lg:block" aria-hidden="true">
      <span
        className="absolute inset-y-0 rounded-full bg-leaf-200"
        style={{ left: `${start * 100}%`, width: `${Math.max(2, (end - start) * 100)}%` }}
      />
      <span className="absolute -top-[3px] h-3 w-[2px] -translate-x-1/2 rounded-full bg-leaf-700" style={{ left: `${point * 100}%` }} />
    </span>
  );
}
