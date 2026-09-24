import { useState, type ReactNode } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import type { SoilContext, WeatherContext } from '../../types/agricultural';
import { AnimatedNumber } from '../common/AnimatedNumber';
import { SegmentedControl } from '../common/SegmentedControl';
import { DATA_TRANSITION, EASE_OUT } from '../../utils/motion';
import { formatNumber } from '../../utils/formatters';

interface EnvironmentalContextProps {
  weather: WeatherContext;
  soil: SoilContext;
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

export function EnvironmentalContext({ weather, soil }: EnvironmentalContextProps) {
  const [tab, setTab] = useState<Tab>('weather');
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
  const heatSlots = Math.max(10, weather.heatExposureDays);
  const awcLevel = soil.awc === 'Low' ? 1 : soil.awc === 'Moderate' ? 2 : 3;

  return (
    <section className="flex h-full flex-col rounded-2xl border border-line bg-surface transition-colors duration-300 hover:border-line-strong p-5 sm:p-6" aria-labelledby="env-heading">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="env-heading" className="text-[16px] font-semibold tracking-[-0.01em] text-ink">
            Environmental context
          </h2>
          <p className="mt-1 text-[14px] text-muted">Conditions around the crop on the selected date.</p>
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
              <Row
                label="Rainfall, last 30 days"
                value={
                  <span className="data text-[20px] font-medium">
                    <AnimatedNumber value={weather.rainfall30Day} decimals={0} />
                    <span className="ml-1 text-[12px] font-normal text-muted">mm</span>
                  </span>
                }
                note={<SwapText value={rainNote} />}
              >
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
                value={
                  <span className="data text-[20px] font-medium">
                    <AnimatedNumber value={weather.gddAccumulated} decimals={0} />
                  </span>
                }
                note={
                  <SwapText
                    value={`${weather.gddComparison >= 0 ? '+' : '−'}${Math.abs(weather.gddComparison)}% vs 10-year pace`}
                  />
                }
              />
              <Row
                label="Heat exposure"
                value={
                  <span className="data text-[20px] font-medium">
                    <AnimatedNumber value={weather.heatExposureDays} decimals={0} />
                    <span className="ml-1 text-[12px] font-normal text-muted">days</span>
                  </span>
                }
                note="Days above 95°F"
              >
                <div className="flex gap-[3px]" aria-hidden="true">
                  {Array.from({ length: heatSlots }, (_, i) => (
                    <motion.span
                      key={i}
                      className="h-2.5 w-1.5 rounded-[2px]"
                      initial={false}
                      animate={{ backgroundColor: i < weather.heatExposureDays ? '#B8574A' : '#F1EFE9' }}
                      transition={{ ...transition, delay: reduce ? 0 : i * 0.02 }}
                    />
                  ))}
                </div>
              </Row>
              <Row
                label="Longest dry spell"
                value={
                  <span className="data text-[20px] font-medium">
                    <AnimatedNumber value={weather.drySpellDays} decimals={0} />
                    <span className="ml-1 text-[12px] font-normal text-muted">days</span>
                  </span>
                }
              />
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
              <Row label="Available water" value={<SwapText value={soil.awc} className="text-[15px] font-medium" />}>
                <span />
                <div className="flex gap-1" aria-hidden="true">
                  {[1, 2, 3].map((level) => (
                    <motion.span
                      key={level}
                      className="h-1.5 w-7 rounded-full"
                      initial={false}
                      animate={{ backgroundColor: level <= awcLevel ? '#4F7DA8' : '#F1EFE9' }}
                      transition={transition}
                    />
                  ))}
                </div>
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
              <Row
                label="pH"
                value={
                  <span className="data text-[18px] font-medium">
                    <AnimatedNumber value={soil.ph} decimals={1} />
                  </span>
                }
              />
              <Row label="Texture" value={<SwapText value={soil.dominantTexture} className="text-[15px] font-medium" />} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <p className="mt-4 border-t border-line pt-3 text-[12px] text-muted">
        Demo values · Candidate source: {tab === 'weather' ? 'PRISM / NOAA' : 'USDA SSURGO'}
      </p>
    </section>
  );
}
