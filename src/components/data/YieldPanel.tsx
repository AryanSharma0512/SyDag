import { motion, useReducedMotion } from 'motion/react';
import type { ContextPart, YieldHistory } from '../../types/agricultural';
import { DATA_TRANSITION } from '../../utils/motion';
import { formatNumber } from '../../utils/formatters';
import { DataPanel, DataTable, Lineage, type Column, type SourceState } from './DataPanel';

/** The backend averages the five most recent years it returns. */
const AVERAGE_YEARS = 5;

type Row = { year: number; yield: number; inAverage: boolean };

const COLUMNS: Column<Row>[] = [
  { key: 'year', label: 'Year', render: (r) => <span className="data">{r.year}</span> },
  { key: 'yield', label: 'Yield (bu/ac)', numeric: true, render: (r) => formatNumber(r.yield, 1) },
  { key: 'avg', label: 'In 5-year average', render: (r) => (r.inAverage ? 'Yes' : <span className="text-muted">No</span>) },
];

interface YieldPanelProps {
  part: ContextPart<YieldHistory> | null;
  state: SourceState;
  showData: boolean;
}

export function YieldPanel({ part, state, showData }: YieldPanelProps) {
  const reduce = useReducedMotion();
  const history = part?.data;
  const rows: Row[] = (history?.years ?? []).map((y, i, all) => ({ ...y, inAverage: i >= all.length - AVERAGE_YEARS }));
  const average = history?.fiveYearAverage ?? null;
  const max = Math.max(...rows.map((r) => r.yield), average ?? 0, 1) * 1.04;
  const windowRows = rows.filter((r) => r.inAverage);
  const countyName = history ? `${history.county.name}, ${history.county.stateCode}` : null;

  return (
    <DataPanel
      id="yield-history"
      source="yieldHistory"
      title="Historical county yields"
      subtitle={
        countyName ? (
          <>
            Corn yields for <span className="font-medium text-ink-soft">{countyName}</span>. These are county-level survey
            averages, not yields measured on this field.
          </>
        ) : (
          'County-level corn yields from the USDA survey, not yields measured on this field.'
        )
      }
      state={state}
      message={part?.message ?? null}
      lineage={
        history && (
          <Lineage
            source={history.source}
            retrievedAt={history.retrievedAt}
            observed={[`County corn yield by year (${history.unit})`]}
            derived={['5-year average']}
          />
        )
      }
    >
      {history && (
        <div className="grid gap-10 md:grid-cols-[220px_minmax(0,1fr)] lg:gap-14">
          <dl className="space-y-5">
            <div>
              <dt className="text-[12px] text-muted">5-year county average</dt>
              <dd className="mt-1">
                {average !== null ? (
                  <>
                    <span className="data-tight text-[30px] font-medium text-ink">{formatNumber(average, 1)}</span>
                    <span className="ml-1.5 text-[13px] text-muted">{history.unit}</span>
                  </>
                ) : (
                  <span className="text-[14px] text-faint">Not enough recent years reported</span>
                )}
              </dd>
              {windowRows.length > 0 && (
                <dd className="data mt-1 text-[12px] text-muted">
                  {windowRows[0].year}–{windowRows[windowRows.length - 1].year}
                </dd>
              )}
            </div>
            <div>
              <dt className="text-[12px] text-muted">County</dt>
              <dd className="mt-1 text-[14px] text-ink">
                {countyName} <span className="data text-[12px] text-muted">FIPS {history.county.fips}</span>
              </dd>
            </div>
            <div>
              <dt className="text-[12px] text-muted">Scale</dt>
              <dd className="mt-1 inline-flex rounded-full border border-leaf-200 bg-leaf-50 px-2.5 py-0.5 text-[12px] font-medium text-leaf-800">
                County-level · not field yield
              </dd>
            </div>
          </dl>

          {showData ? (
            <DataTable caption={`Corn yield by year, ${countyName}`} columns={COLUMNS} rows={rows} rowKey={(r) => String(r.year)} />
          ) : (
            <div>
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px] text-muted">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-[3px] bg-leaf-600" aria-hidden="true" /> In 5-year average
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-[3px] bg-leaf-200" aria-hidden="true" /> Earlier years
                </span>
                {average !== null && (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-3 w-px bg-ink/50" aria-hidden="true" /> 5-year average
                  </span>
                )}
              </div>
              <div className="relative mt-5">
                <ul className="space-y-2" aria-label={`Corn yield by year, ${history.unit}`}>
                  {rows.map((r) => (
                    <li key={r.year} className="grid grid-cols-[3rem_1fr_3.5rem] items-center gap-3">
                      <span className={`data text-[12px] ${r.inAverage ? 'text-ink' : 'text-muted'}`}>{r.year}</span>
                      <div className="h-3" aria-hidden="true">
                        <motion.div
                          className={`h-full w-full origin-left rounded-r-[4px] ${r.inAverage ? 'bg-leaf-600' : 'bg-leaf-200'}`}
                          initial={reduce ? false : { scaleX: 0 }}
                          animate={{ scaleX: r.yield / max }}
                          transition={reduce ? { duration: 0 } : DATA_TRANSITION}
                        />
                      </div>
                      <span className="data text-right text-[12px] text-ink-soft tabular-nums">{formatNumber(r.yield, 1)}</span>
                    </li>
                  ))}
                </ul>
                {average !== null && (
                  <div className="pointer-events-none absolute inset-y-[-4px] right-[4.25rem] left-[3.75rem]" aria-hidden="true">
                    <div className="absolute inset-y-0 w-px bg-ink/40" style={{ left: `${(average / max) * 100}%` }} />
                  </div>
                )}
              </div>
              <p className="mt-4 text-[12px] text-muted">Corn for grain, bushels per acre, from the NASS annual county survey.</p>
            </div>
          )}
        </div>
      )}
    </DataPanel>
  );
}
