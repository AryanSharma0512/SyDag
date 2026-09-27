import { useEffect, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ChevronDown } from 'lucide-react';
import type { OutlookCategory, OutlookHorizon, WeatherOutlook, WeatherOutlookState } from '../../types/weatherOutlook';
import type { TrialSite } from '../../types/sites';
import { getWeatherOutlook, horizonLabel, OUTLOOK_HORIZONS } from '../../services/weatherOutlook';
import { formatDay, formatNumber } from '../../utils/formatters';
import { DATA_TRANSITION, EASE_OUT } from '../../utils/motion';
import { SegmentedControl } from '../common/SegmentedControl';

interface WeatherOutlookCardProps {
  site: TrialSite;
  asOfDate: string;
  plantingDate?: string;
  isPresentationMode?: boolean;
}

/** Diverging: warm for adverse, neutral gray for typical, green for favorable. Labels carry identity too. */
const CATEGORY: Record<OutlookCategory, { label: string; fill: string; dot: string }> = {
  adverse: { label: 'Adverse', fill: 'bg-stress-500', dot: 'bg-stress-500' },
  typical: { label: 'Typical', fill: 'bg-[#B4BAC2]', dot: 'bg-[#B4BAC2]' },
  favorable: { label: 'Favorable', fill: 'bg-leaf-500', dot: 'bg-leaf-500' },
};
const ORDER: OutlookCategory[] = ['adverse', 'typical', 'favorable'];

const HORIZON_OPTIONS = OUTLOOK_HORIZONS.map((h) => ({
  value: String(h),
  label: h === 'season' ? 'Season' : `${h}d`,
}));

function range(low: number, high: number, decimals: number): string {
  const a = decimals ? low.toFixed(decimals) : formatNumber(Math.max(0, low));
  const b = decimals ? high.toFixed(decimals) : formatNumber(Math.max(0, high));
  return a === b ? a : `${a}–${b}`;
}

/**
 * Historical weather outlook for the forecast date (GET /api/weather-outlook via
 * services/weatherOutlook). What past seasons brought after this date, not a weather
 * forecast, and kept separate from the yield forecast: the two are not coupled yet.
 */
export function WeatherOutlookCard({ site, asOfDate, plantingDate, isPresentationMode = false }: WeatherOutlookCardProps) {
  const reduce = useReducedMotion();
  const [horizon, setHorizon] = useState<OutlookHorizon>(60);
  const [state, setState] = useState<WeatherOutlookState>({ status: 'loading' });
  const [showDetail, setShowDetail] = useState(false);
  const librarySite = site.weather?.librarySite;

  useEffect(() => {
    if (!librarySite) {
      setState({ status: 'unavailable', reason: 'This server has no weather history for this location.' });
      return;
    }
    let active = true;
    setState((current) => (current.status === 'success' ? current : { status: 'loading' }));
    getWeatherOutlook(librarySite, asOfDate, horizon, plantingDate)
      .then((outlook) => active && setState({ status: 'success', outlook }))
      .catch(
        (err: unknown) => active && setState({ status: 'unavailable', reason: err instanceof Error ? err.message : String(err) }),
      );
    return () => {
      active = false;
    };
  }, [librarySite, asOfDate, horizon, plantingDate]);

  const outlook = state.status === 'success' ? state.outlook : null;
  const stale = outlook !== null && (outlook.asOfDate !== asOfDate || outlook.horizon !== horizon);
  const text = isPresentationMode ? 'text-[16px]' : 'text-[14px]';

  return (
    <section aria-labelledby="outlook-heading" className="flex h-full flex-col">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2
            id="outlook-heading"
            className={`font-semibold tracking-[-0.015em] text-ink ${isPresentationMode ? 'text-[24px]' : 'text-[19px]'}`}
          >
            Historical weather outlook
          </h2>
          <p className={`mt-1 text-muted ${text}`}>
            {horizonLabel(horizon)} after <span className="data">{formatDay(asOfDate)}</span>
            {outlook && !stale && (
              <>
                {' '}
                (to <span className="data">{formatDay(outlook.horizonEnd)}</span>)
              </>
            )}
          </p>
        </div>
        <SegmentedControl
          ariaLabel="Outlook horizon"
          size="sm"
          mono
          options={HORIZON_OPTIONS}
          value={String(horizon)}
          onChange={(v) => setHorizon(v === 'season' ? 'season' : (Number(v) as OutlookHorizon))}
        />
      </div>

      {state.status === 'unavailable' ? (
        <p className="mt-6 rounded-xl border border-dashed border-line-strong px-4 py-5 text-[14px] text-muted">{state.reason}</p>
      ) : !outlook ? (
        <div className="mt-6 space-y-3" aria-busy="true" aria-label="Loading weather outlook">
          <div className="ss-skeleton h-9 rounded-lg" />
          <div className="ss-skeleton h-4 w-2/3 rounded" />
          <div className="ss-skeleton h-16 rounded-lg" />
        </div>
      ) : (
        <motion.div className="mt-5 flex flex-1 flex-col" animate={{ opacity: stale ? 0.45 : 1 }} transition={{ duration: 0.15 }}>
          {outlook.probabilities ? (
            <Probabilities outlook={outlook} reduce={!!reduce} large={isPresentationMode} />
          ) : (
            <p className="text-[14px] text-muted">
              Past seasons could not be sorted into adverse, typical and favorable here
              {outlook.categoryNote ? `: ${outlook.categoryNote}` : '.'}
            </p>
          )}

          <p className={`mt-4 text-ink-soft ${text}`}>
            Based on weather outcomes observed after this point in{' '}
            <span className="data font-medium text-ink">{outlook.historicalSeasons}</span> previous seasons
            {outlook.firstSeason && outlook.lastSeason ? (
              <>
                {' '}
                (<span className="data">{outlook.firstSeason}</span>–<span className="data">{outlook.lastSeason}</span>)
              </>
            ) : null}
            .{outlook.exploratory && ' Exploratory: fewer than 20 seasons.'}
          </p>

          {outlook.outcomes.length > 0 && (
            <div className="mt-4 border-t border-line pt-4">
              <p className="text-[12px] text-muted">What those seasons brought (middle 60% of seasons)</p>
              <dl className={`mt-2 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-3 ${text}`}>
                {outlook.outcomes
                  .filter((o) => o.id === 'rain' || o.id === 'heatDays' || o.id === 'gdd')
                  .map((o) => (
                    <div key={o.id} className="flex items-baseline justify-between gap-2 sm:block">
                      <dt className="text-muted">{o.label}</dt>
                      <dd className="data font-medium text-ink">
                        {range(o.low, o.high, o.decimals)}{' '}
                        <span className="font-normal text-muted">{o.unit === 'GDD' ? '' : o.unit}</span>
                      </dd>
                    </div>
                  ))}
              </dl>
            </div>
          )}

          {!isPresentationMode && (
            <div className="mt-auto pt-4">
              <button
                type="button"
                onClick={() => setShowDetail((v) => !v)}
                aria-expanded={showDetail}
                className="-mx-1.5 inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[13px] font-medium text-ink-soft hover:bg-mist hover:text-ink"
              >
                How to read this
                <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${showDetail ? 'rotate-180' : ''}`} />
              </button>
              <AnimatePresence initial={false}>
                {showDetail && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25, ease: EASE_OUT }}
                    className="overflow-hidden"
                  >
                    <OutlookDetail outlook={outlook} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </motion.div>
      )}
    </section>
  );
}

function Probabilities({ outlook, reduce, large }: { outlook: WeatherOutlook; reduce: boolean; large: boolean }) {
  const p = outlook.probabilities!;
  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;
  return (
    <div>
      <div
        className="flex h-3 w-full gap-[2px] overflow-hidden rounded-full"
        role="img"
        aria-label={ORDER.map((c) => `${CATEGORY[c].label} ${p[c]}%`).join(', ')}
      >
        {ORDER.map((c) => (
          <motion.div
            key={c}
            className={`h-full ${CATEGORY[c].fill}`}
            initial={false}
            animate={{ flexGrow: Math.max(p[c], 0.5) }}
            style={{ flexBasis: 0 }}
            transition={transition}
            title={`${CATEGORY[c].label}: ${p[c]}%`}
          />
        ))}
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-3">
        {ORDER.map((c) => (
          <div key={c}>
            <dt className={`flex items-center gap-1.5 text-muted ${large ? 'text-[15px]' : 'text-[13px]'}`}>
              <span className={`h-2 w-2 rounded-full ${CATEGORY[c].dot}`} aria-hidden="true" />
              {CATEGORY[c].label}
            </dt>
            <dd className={`data mt-0.5 font-medium text-ink ${large ? 'text-[34px]' : 'text-[26px]'}`}>
              {p[c]}
              <span className="text-[0.6em] text-muted">%</span>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function OutlookDetail({ outlook }: { outlook: WeatherOutlook }) {
  return (
    <div className="mt-3 space-y-3 rounded-xl bg-mist/60 p-4 text-[13px] leading-relaxed text-ink-soft">
      <p>
        This is a historical outlook, not a weather forecast: it shows how often the weather that followed this date in past
        seasons turned out adverse, typical or favorable for maize.{' '}
        {outlook.equalWeights
          ? 'At this location every past season counts equally.'
          : 'At this location, past seasons that resembled this one so far count more.'}
      </p>
      {outlook.categoryBasis && (
        <p>
          <span className="font-medium text-ink">What adverse and favorable mean here.</span> {outlook.categoryBasis}
          {outlook.categoryProvisional && ' This scoring is provisional until the yield model scores each season.'}
        </p>
      )}
      {outlook.representative.length > 0 && (
        <p>
          <span className="font-medium text-ink">Example seasons.</span>{' '}
          {outlook.representative
            .map(
              (r) =>
                `${CATEGORY[r.category].label.toLowerCase()} ${r.season}${r.rainIn != null ? ` (${r.rainIn.toFixed(1)} in of rain)` : ''}`,
            )
            .join(', ')}
          .
        </p>
      )}
      <p className="text-muted">
        Station: {outlook.stationName ?? 'unknown'}
        {outlook.stationSource ? `, ${outlook.stationSource}` : ''}. The yield forecast above does not yet use these scenarios;
        the two are shown separately.
      </p>
    </div>
  );
}
