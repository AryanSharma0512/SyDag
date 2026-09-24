import { useState, type ReactNode } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import type { ObservedWeather, SoilContext, SoilProfile, WeatherContext, WeatherSummary } from '../../types/agricultural';
import { AnimatedNumber } from '../common/AnimatedNumber';
import { SegmentedControl } from '../common/SegmentedControl';
import { DATA_TRANSITION, EASE_OUT } from '../../utils/motion';
import { formatDay, formatNumber, formatRetrieved } from '../../utils/formatters';

interface EnvironmentalContextProps {
  /** Demo scenario values, shown when public data for the field isn't available. */
  weather: WeatherContext;
  soil: SoilContext;
  /** Selected forecast date (ISO); picks the matching observed-weather summary. */
  asOf: string;
  /** Public data for the field's coordinates (NOAA NCEI, USDA SSURGO). */
  observed?: ObservedWeather | null;
  soilProfile?: SoilProfile | null;
  /** Why public weather or soil data is missing, or a note about its freshness. */
  weatherNote?: string | null;
  soilNote?: string | null;
}

type Tab = 'weather' | 'soil';

/** Swaps text values with a short vertical crossfade so changes are noticed without shouting. */
function SwapText({ value, className = '' }: { value: string; className?: string }) {
  return (
    <span className={`relative inline-grid overflow-hidden ${className}`}>
      <AnimatePresence initial={false} mode="popLayout">
        <motion.span
          key={value}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.2, ease: EASE_OUT }}
        >
          {value}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}

function Row({ label, value, note, children }: { label: string; value: ReactNode; note?: ReactNode; children?: ReactNode }) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-baseline gap-x-4 border-t border-line py-3.5 first:border-t-0 first:pt-1">
      <div className="text-[14px] text-ink-soft">{label}</div>
      <div className="text-right text-ink">{value}</div>
      {(note || children) && (
        <div className="col-span-2 mt-1.5 flex items-center justify-between gap-4">
          <span className="text-[13px] text-muted">{note}</span>
          {children}
        </div>
      )}
    </div>
  );
}

function Measure({ value, decimals = 0, unit, size = 20 }: { value: number; decimals?: number; unit?: string; size?: 18 | 20 }) {
  return (
    <span className={`data font-medium ${size === 20 ? 'text-[20px]' : 'text-[18px]'}`}>
      <AnimatedNumber value={value} decimals={decimals} />
      {unit && <span className="ml-1 text-[12px] font-normal text-muted">{unit}</span>}
    </span>
  );
}

function HeatSlots({ days }: { days: number }) {
  const reduce = useReducedMotion();
  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;
  return (
    <div className="flex gap-[3px]" aria-hidden="true">
      {Array.from({ length: Math.max(10, days) }, (_, i) => (
        <motion.span
          key={i}
          className="h-2.5 w-1.5 rounded-[2px]"
          initial={false}
          animate={{ backgroundColor: i < days ? '#B8574A' : '#F1EFE9' }}
          transition={{ ...transition, delay: reduce ? 0 : i * 0.02 }}
        />
      ))}
    </div>
  );
}

function WaterLevel({ level }: { level: 'Low' | 'Moderate' | 'High' }) {
  const reduce = useReducedMotion();
  const filled = level === 'Low' ? 1 : level === 'Moderate' ? 2 : 3;
  return (
    <div className="flex gap-1" aria-hidden="true">
      {[1, 2, 3].map((n) => (
        <motion.span
          key={n}
          className="h-1.5 w-7 rounded-full"
          initial={false}
          animate={{ backgroundColor: n <= filled ? '#4F7DA8' : '#F1EFE9' }}
          transition={reduce ? { duration: 0 } : DATA_TRANSITION}
        />
      ))}
    </div>
  );
}

/** Source line under the panel. A filled dot marks public data; demo values get none. */
function SourceNote({ live, children }: { live: boolean; children: ReactNode }) {
  return (
    <p className="mt-4 flex items-baseline gap-2 border-t border-line pt-3 text-[12px] leading-relaxed text-muted">
      {live && <span className="mt-[5px] h-1.5 w-1.5 shrink-0 self-start rounded-full bg-rain-500" aria-hidden="true" />}
      <span>{children}</span>
    </p>
  );
}

function DemoWeather({ weather }: { weather: WeatherContext }) {
  const reduce = useReducedMotion();
  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;
  const normalRain = weather.rainfall30Day / (1 + weather.rainfallComparison / 100);
  const rainScale = Math.max(weather.rainfall30Day, normalRain) * 1.1;
  const rainNote =
    weather.rainfallComparison < 0
      ? `${Math.abs(weather.rainfallComparison)}% below normal`
      : weather.rainfallComparison > 0
        ? `${weather.rainfallComparison}% above normal`
        : 'Near normal';
  return (
    <>
      <Row label="Rainfall, last 30 days" value={<Measure value={weather.rainfall30Day} unit="mm" />} note={<SwapText value={rainNote} />}>
        <div className="relative h-1.5 w-28 overflow-x-clip rounded-full bg-mist" aria-hidden="true">
          <motion.div
            className="absolute inset-y-0 left-0 w-full origin-left rounded-full bg-rain-500/80"
            initial={false}
            animate={{ scaleX: weather.rainfall30Day / rainScale }}
            transition={transition}
          />
          <motion.div className="absolute inset-0" initial={false} animate={{ x: `${(normalRain / rainScale) * 100}%` }} transition={transition}>
            <span className="absolute -top-1 left-0 h-3.5 w-[2px] -ml-px rounded-full bg-ink-soft" title="30-year normal" />
          </motion.div>
        </div>
      </Row>
      <Row
        label="Growing degree days"
        value={<Measure value={weather.gddAccumulated} />}
        note={<SwapText value={`${weather.gddComparison >= 0 ? '+' : '−'}${Math.abs(weather.gddComparison)}% vs 10-year pace`} />}
      />
      <Row label="Heat exposure" value={<Measure value={weather.heatExposureDays} unit="days" />} note="Days above 95°F">
        <HeatSlots days={weather.heatExposureDays} />
      </Row>
      <Row label="Longest dry spell" value={<Measure value={weather.drySpellDays} unit="days" />} />
    </>
  );
}

function LiveWeather({ summary }: { summary: WeatherSummary }) {
  const reduce = useReducedMotion();
  const transition = reduce ? { duration: 0 } : DATA_TRANSITION;
  const since = formatDay(summary.seasonStart);
  // Fixed scale so bars compare across dates; 150 mm is a very wet month in the Corn Belt.
  const rainScale = Math.max(150, summary.rainfallLast30DaysMm * 1.05);
  return (
    <>
      <Row
        label="Rainfall, last 30 days"
        value={<Measure value={summary.rainfallLast30DaysMm} unit="mm" />}
        note={<SwapText value={`${formatNumber(summary.rainfallLast7DaysMm)} mm in the last 7 days`} />}
      >
        <div className="relative h-1.5 w-28 overflow-x-clip rounded-full bg-mist" aria-hidden="true">
          <motion.div
            className="absolute inset-y-0 left-0 w-full origin-left rounded-full bg-rain-300"
            initial={false}
            animate={{ scaleX: summary.rainfallLast30DaysMm / rainScale }}
            transition={transition}
          />
          <motion.div
            className="absolute inset-y-0 left-0 w-full origin-left rounded-full bg-rain-600"
            initial={false}
            animate={{ scaleX: summary.rainfallLast7DaysMm / rainScale }}
            transition={transition}
          />
        </div>
      </Row>
      <Row label="Growing degree days" value={<Measure value={summary.gddSinceSeasonStart} />} note={`Since ${since}, base 50°F`} />
      <Row label="Heat exposure" value={<Measure value={summary.heatDays} unit="days" />} note={`At 95°F or hotter since ${since}`}>
        <HeatSlots days={summary.heatDays} />
      </Row>
      <Row
        label="Longest dry spell"
        value={<Measure value={summary.longestDrySpellDays} unit="days" />}
        note={`Under 1 mm of rain a day, since ${since}`}
      />
      {summary.avgTempLast30DaysF !== null && (
        <Row label="Average temperature" value={<Measure value={summary.avgTempLast30DaysF} decimals={1} unit="°F" />} note="Last 30 days" />
      )}
    </>
  );
}

function DemoSoil({ soil }: { soil: SoilContext }) {
  return (
    <>
      <Row label="Available water" value={<SwapText value={soil.awc} className="text-[15px] font-medium" />}>
        <span />
        <WaterLevel level={soil.awc} />
      </Row>
      <Row label="Drainage" value={<SwapText value={soil.drainage} className="text-[15px] font-medium" />} />
      <Row
        label="Organic matter"
        value={
          <span className="data text-[18px] font-medium">
            <AnimatedNumber value={soil.organicMatter} decimals={1} format={(v) => `${formatNumber(v, 1)}%`} />
          </span>
        }
      />
      <Row label="pH" value={<Measure value={soil.ph} decimals={1} size={18} />} />
      <Row label="Texture" value={<SwapText value={soil.dominantTexture} className="text-[15px] font-medium" />} />
    </>
  );
}

function LiveSoil({ profile }: { profile: SoilProfile }) {
  const seriesNote = [profile.texture, `${formatNumber(profile.componentPercent)}% of the mapped area`].filter(Boolean).join(' · ');
  return (
    <>
      <Row label="Soil series" value={<SwapText value={profile.series} className="text-[15px] font-medium" />} note={<SwapText value={seriesNote} />} />
      {profile.drainage && (
        <Row
          label="Drainage"
          value={<SwapText value={profile.drainage} className="text-[15px] font-medium" />}
          note={profile.hydrologicGroup ? `Hydrologic group ${profile.hydrologicGroup}` : undefined}
        />
      )}
      {profile.availableWaterClass && (
        <Row
          label="Available water"
          value={<SwapText value={profile.availableWaterClass} className="text-[15px] font-medium" />}
          note={profile.availableWaterStorageCm !== null ? `${formatNumber(profile.availableWaterStorageCm, 1)} cm in the top 100 cm` : undefined}
        >
          <WaterLevel level={profile.availableWaterClass} />
        </Row>
      )}
      {profile.organicMatter !== null && (
        <Row
          label="Organic matter"
          value={
            <span className="data text-[18px] font-medium">
              <AnimatedNumber value={profile.organicMatter} decimals={1} format={(v) => `${formatNumber(v, 1)}%`} />
            </span>
          }
          note="Surface layer"
        />
      )}
      {profile.ph !== null && <Row label="pH" value={<Measure value={profile.ph} decimals={1} size={18} />} />}
      {profile.rootZoneDepthCm !== null && (
        <Row label="Root zone" value={<Measure value={profile.rootZoneDepthCm} unit="cm" size={18} />} note="Depth roots can use" />
      )}
    </>
  );
}

export function EnvironmentalContext({ weather, soil, asOf, observed, soilProfile, weatherNote, soilNote }: EnvironmentalContextProps) {
  const [tab, setTab] = useState<Tab>('weather');
  const summary = observed?.summaries.find((s) => s.asOf === asOf) ?? null;

  const note =
    tab === 'weather' ? (
      summary && observed ? (
        <SourceNote live>
          NOAA NCEI daily observations · {observed.station.name}, {formatNumber(observed.station.distanceKm, 1)} km away ·
          retrieved {formatRetrieved(observed.retrievedAt)}
          {summary.dataCompleteness < 0.8 && ` · ${Math.round(summary.dataCompleteness * 100)}% of days reported`}
          {weatherNote && ` · ${weatherNote}`}
        </SourceNote>
      ) : (
        <SourceNote live={false}>Demo values{weatherNote && ` · ${weatherNote}`}</SourceNote>
      )
    ) : soilProfile ? (
      <SourceNote live>
        USDA NRCS SSURGO · {soilProfile.mapUnitName} · retrieved {formatRetrieved(soilProfile.retrievedAt)}
        {soilNote && ` · ${soilNote}`}
      </SourceNote>
    ) : (
      <SourceNote live={false}>Demo values{soilNote && ` · ${soilNote}`}</SourceNote>
    );

  return (
    <section className="flex h-full flex-col rounded-2xl border border-line bg-surface transition-colors duration-300 hover:border-line-strong p-5 sm:p-6" aria-labelledby="env-heading">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="env-heading" className="text-[16px] font-semibold tracking-[-0.01em] text-ink">
            Environmental context
          </h2>
          <p className="mt-1 text-[14px] text-muted">
            {tab === 'weather' ? 'Conditions around the crop on the selected date.' : 'The soil mapped at this field.'}
          </p>
        </div>
        <SegmentedControl
          ariaLabel="Context type"
          size="sm"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'weather', label: 'Weather' },
            { value: 'soil', label: 'Soil' },
          ]}
        />
      </div>

      <div className="relative mt-4 flex-1">
        <AnimatePresence initial={false} mode="wait">
          {tab === 'weather' ? (
            <motion.div
              key="weather"
              role="tabpanel"
              aria-label="Weather"
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 6 }}
              transition={{ duration: 0.16, ease: EASE_OUT }}
            >
              {summary ? <LiveWeather summary={summary} /> : <DemoWeather weather={weather} />}
            </motion.div>
          ) : (
            <motion.div
              key="soil"
              role="tabpanel"
              aria-label="Soil"
              initial={{ opacity: 0, x: 6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              transition={{ duration: 0.16, ease: EASE_OUT }}
            >
              {soilProfile ? <LiveSoil profile={soilProfile} /> : <DemoSoil soil={soil} />}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {note}
    </section>
  );
}
