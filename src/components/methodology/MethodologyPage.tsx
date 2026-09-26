import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight } from 'lucide-react';
import type { DataSource, FieldForecast, ModelInfo } from '../../types/agricultural';
import { getForecast } from '../../services/forecasts';
import { getFields, pickDefaultFieldId } from '../../services/fields';
import { getDataSources } from '../../services/sources';
import { getModels } from '../../services/evaluation';
import { APP_CONFIG } from '../../config/appConfig';
import { EASE_OUT } from '../../utils/motion';
import { formatDay } from '../../utils/formatters';
import { imageryLabel, passDates } from '../../utils/imagery';
import { Link } from '../../utils/router';
import { Reveal } from '../common/Reveal';
import { DataBadge } from '../common/DataBadge';
import { PipelineAnimation } from './PipelineAnimation';
import { UncertaintyDemo } from './UncertaintyDemo';

const SOURCE_BADGE: Record<DataSource['role'], string> = {
  challenge: 'Challenge',
  practice: 'Practice data',
  public: 'Connected',
  model: 'Model-derived',
  candidate: 'Candidate',
};

export function MethodologyPage() {
  const reduce = useReducedMotion();
  const [forecast, setForecast] = useState<FieldForecast | null>(null);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);

  useEffect(() => {
    let active = true;
    getFields()
      .then((fields) => {
        const id = pickDefaultFieldId(fields);
        return id ? getForecast(id) : null;
      })
      .then((data) => {
        if (!active || !data) return;
        setForecast(data);
        return getDataSources(data).then((list) => active && setSources(list));
      })
      .catch(() => active && setSources([]));
    getModels()
      .then((list) => active && setModels(list))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const snaps = forecast?.snapshots ?? [];
  const passes = forecast ? passDates(forecast) : [];
  const maeFor = (date: string) => models.find((m) => m.asOf === date.slice(5))?.mae;
  const hasMae = snaps.some((snap) => maeFor(snap.date) !== undefined);

  return (
    <div className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
      <header className="pt-14 pb-12 sm:pt-20 sm:pb-16">
        <motion.p
          className="text-[13px] font-medium text-leaf-700"
          initial={reduce ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: EASE_OUT }}
        >
          Methodology
        </motion.p>
        <motion.h1
          className="mt-3 text-[40px] leading-[1.05] font-semibold tracking-[-0.035em] text-ink sm:text-[54px]"
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE_OUT, delay: 0.05 }}
        >
          How SoilSignal works
        </motion.h1>
        <motion.p
          className="mt-5 max-w-2xl text-[17px] leading-relaxed text-pretty text-muted sm:text-[18px]"
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE_OUT, delay: 0.12 }}
        >
          For each plot, we combine the field record with the satellite observations available by that date. Each
          forecast is an estimate of final yield with a 90% range.
        </motion.p>
      </header>

      <section aria-labelledby="pipeline-heading">
        <Reveal>
          <h2 id="pipeline-heading" className="text-[22px] font-semibold tracking-[-0.02em] text-ink">
            From plot imagery to yield prediction
          </h2>
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
            Satellite imagery and the field record (planting date, nitrogen rate, irrigation, hybrid, site and season)
            become features computed only from data available by each forecast date. NOAA weather and USDA soil are
            added as context. One model per forecast date turns the features into an estimate and a range.{' '}
            {APP_CONFIG.demoMode
              ? 'This build runs on demo data.'
              : 'The data sources table below lists every input the deployed models use.'}
          </p>
        </Reveal>
        <div className="mt-10">
          <PipelineAnimation />
        </div>
      </section>

      <section className="mt-24" aria-labelledby="season-heading">
        <Reveal>
          <h2 id="season-heading" className="text-[22px] font-semibold tracking-[-0.02em] text-ink">
            Accuracy changes as more imagery arrives
          </h2>
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
            Satellite passes fall on different dates at each site, so the season is counted in passes, not months.
            {forecast && ` Each row is one forecast date for ${forecast.field.name}.`}
          </p>
        </Reveal>
        <Reveal className="mt-8 overflow-x-auto">
          {snaps.length > 0 ? (
            <table className="w-full min-w-[480px] text-left">
              <thead>
                <tr className="border-b border-line-strong text-[13px] text-muted">
                  <th scope="col" className="py-3 pr-6 font-medium">Forecast date</th>
                  <th scope="col" className="py-3 pr-6 font-medium">Imagery available</th>
                  <th scope="col" className="py-3 pr-6 text-right font-medium">90% range</th>
                  {hasMae && <th scope="col" className="py-3 text-right font-medium">Validation MAE</th>}
                </tr>
              </thead>
              <tbody>
                {snaps.map((snap) => {
                  const mae = maeFor(snap.date);
                  return (
                    <tr key={snap.id} className="border-b border-line">
                      <td className="data py-3 pr-6 text-[15px] text-ink">{snap.displayDate}</td>
                      <td className="py-3 pr-6 text-[15px] text-ink-soft">{imageryLabel(passes, snap.date)}</td>
                      <td className="data py-3 pr-6 text-right text-[15px] text-ink tabular-nums">
                        ±{((snap.upperBound - snap.lowerBound) / 2).toFixed(1)}
                        <span className="ml-1 text-[12px] text-muted">bu/ac</span>
                      </td>
                      {hasMae && (
                        <td className="data py-3 text-right text-[15px] text-ink tabular-nums">
                          {mae !== undefined ? mae.toFixed(1) : '—'}
                          <span className="ml-1 text-[12px] text-muted">bu/ac</span>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="ss-skeleton h-48 rounded-lg" />
          )}
          {passes.length > 0 && (
            <p className="mt-4 text-[13px] text-muted">
              Satellite passes for this plot: <span className="data">{passes.map(formatDay).join(', ')}</span>.
              {hasMae && ' Validation MAE is the cross-validation error of the model used on that date.'}
            </p>
          )}
        </Reveal>
      </section>

      <section className="mt-24" aria-labelledby="uncertainty-heading">
        <Reveal>
          <h2 id="uncertainty-heading" className="text-[22px] font-semibold tracking-[-0.02em] text-ink">
            How much error should we expect?
          </h2>
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
            Every forecast carries a 90% range, set from the model's validation errors: the final yield should fall
            inside it about nine times in ten. Pick an imagery stage to compare ranges.
          </p>
        </Reveal>
        <Reveal className="mt-8 rounded-2xl border border-line bg-surface p-5 sm:p-8">
          {forecast ? <UncertaintyDemo forecast={forecast} /> : <div className="h-[320px]" />}
        </Reveal>
      </section>

      <section className="mt-24" aria-labelledby="sources-heading">
        <Reveal>
          <h2 id="sources-heading" className="text-[22px] font-semibold tracking-[-0.02em] text-ink">
            Data sources
          </h2>
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
            The trial data behind the forecasts, the public data looked up for each plot, and the models.
          </p>
        </Reveal>
        <Reveal className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[520px] text-left">
            <thead>
              <tr className="border-b border-line-strong text-[13px] text-muted">
                <th scope="col" className="py-3 pr-6 font-medium">Source</th>
                <th scope="col" className="py-3 pr-6 font-medium">Purpose</th>
                <th scope="col" className="py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id} className="border-b border-line">
                  <td className="py-3.5 pr-6 text-[15px] font-medium text-ink">{s.shortName}</td>
                  <td className="py-3.5 pr-6 text-[15px] text-ink-soft">{s.purpose}</td>
                  <td className="py-3.5">
                    <DataBadge variant={s.role} label={SOURCE_BADGE[s.role]} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Reveal>
      </section>

      <Reveal className="mt-24 flex flex-col items-start justify-between gap-6 border-t border-line pt-10 sm:flex-row sm:items-center">
        <p className="text-[18px] font-medium tracking-[-0.01em] text-ink">See it applied to the current trial.</p>
        <Link
          to="dashboard"
          className="lift group inline-flex items-center gap-2 rounded-full bg-leaf-700 px-5 py-2.5 text-[15px] font-medium text-white hover:bg-leaf-800 hover:shadow-lift"
        >
          Review plots
          <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
        </Link>
      </Reveal>
    </div>
  );
}
