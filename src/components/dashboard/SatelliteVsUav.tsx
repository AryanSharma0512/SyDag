import { Plane, Satellite } from 'lucide-react';
import type { FinalResults, PlotUav } from '../../types/results';
import type { TrialSite } from '../../types/sites';

interface SatelliteVsUavProps {
  results: FinalResults | null;
  /** The selected plot's own predictions under each variant, when the results carry them. */
  plotUav?: PlotUav | null;
  /** Every trial site, to say where UAV imagery exists in the challenge data. */
  sites: TrialSite[];
  isPresentationMode?: boolean;
}

const fmt = (v: number | null | undefined) => (v == null ? '—' : Math.round(v).toString());
const signed = (v: number, digits: number) => `${v > 0 ? '+' : v < 0 ? '−' : '±'}${Math.abs(v).toFixed(digits)}`;

/**
 * Is an extra UAV flight worth it? Satellite is the base layer; UAV is an optional
 * refinement. Numbers appear only for a matched experiment (same plots, dates,
 * validation split and model framework); nothing is estimated in the meantime, and no
 * per-plot UAV forecast or dollar value is shown unless the results supply one.
 */
export function SatelliteVsUav({ results, plotUav, sites, isPresentationMode = false }: SatelliteVsUavProps) {
  const uav = results?.status === 'ready' ? results.uav : null;
  const matched = !!uav?.matched;
  const delta = matched ? uav!.satellitePlusUav.mae - uav!.satelliteOnly.mae : null;
  const r2Delta =
    matched && uav!.satellitePlusUav.r2 != null && uav!.satelliteOnly.r2 != null
      ? uav!.satellitePlusUav.r2 - uav!.satelliteOnly.r2
      : null;
  const uavSites = sites.filter((s) => s.seasons.some((season) => season.uav.plotImages > 0));
  const siteName = (id: string) => sites.find((s) => s.id.toLowerCase() === id.toLowerCase())?.name ?? id;
  const text = isPresentationMode ? 'text-[16px]' : 'text-[14px]';
  const big = isPresentationMode ? 'text-[34px]' : 'text-[26px]';
  const showPlot = matched && plotUav != null;

  const panels = [
    {
      key: 'satellite',
      title: 'Satellite only',
      role: 'Routine, scalable monitoring for every field',
      icon: Satellite,
      predicted: plotUav?.satelliteOnly,
      variant: uav?.satelliteOnly,
      tone: 'border-line',
    },
    {
      key: 'uav',
      title: 'Satellite + UAV',
      role: 'Optional higher-resolution refinement',
      icon: Plane,
      predicted: plotUav?.satellitePlusUav,
      variant: uav?.satellitePlusUav,
      tone: 'border-dashed border-line-strong',
    },
  ];

  return (
    <section aria-labelledby="uav-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2
          id="uav-heading"
          className={`font-semibold tracking-[-0.015em] text-ink ${isPresentationMode ? 'text-[24px]' : 'text-[19px]'}`}
        >
          Satellite vs UAV
        </h2>
        <p className="text-[13px] text-muted">Is an extra drone flight worth collecting?</p>
      </div>
      <p className={`mt-1 max-w-2xl text-muted ${text}`}>
        SoilSignal runs on satellite imagery alone. UAV imagery is optional: it is worth paying for only if it lowers the forecast
        error enough to matter.
        {matched && ' The numbers below come from a separate matched experiment, not from the forecast above.'}
      </p>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {panels.map(({ key, title, role, icon: Icon, predicted, variant, tone }) => (
          <div key={key} className={`rounded-xl border bg-surface p-5 ${tone}`}>
            <div className="flex items-center gap-2">
              <Icon className="h-4 w-4 text-muted" aria-hidden="true" />
              <h3 className="text-[13px] font-semibold tracking-[0.06em] text-ink uppercase">{title}</h3>
            </div>
            <p className="mt-1 text-[13px] text-muted">{role}</p>
            <dl className={`mt-4 grid gap-4 ${showPlot ? 'grid-cols-2' : 'grid-cols-1'}`}>
              {showPlot && (
                <div>
                  <dt className="text-[13px] text-muted">Predicted yield</dt>
                  <dd className={`data mt-1 font-medium text-ink ${big}`}>
                    {fmt(predicted)}
                    {predicted != null && <span className="ml-1 text-[0.5em] text-muted">bu/ac</span>}
                  </dd>
                </div>
              )}
              <div>
                <dt className="text-[13px] text-muted">Typical validation error (MAE)</dt>
                <dd className={`data mt-1 font-medium text-ink ${big}`}>
                  {matched && variant ? variant.mae.toFixed(2) : '—'}
                  {matched && variant && <span className="ml-1 text-[0.5em] text-muted">bu/ac</span>}
                </dd>
                {matched && variant && (variant.rmse != null || variant.r2 != null) && (
                  <dd className="data mt-1 text-[13px] text-muted">
                    {[variant.rmse != null && `RMSE ${variant.rmse.toFixed(2)}`, variant.r2 != null && `R² ${variant.r2.toFixed(3)}`]
                      .filter(Boolean)
                      .join(' · ')}
                  </dd>
                )}
              </div>
            </dl>
          </div>
        ))}
      </div>

      {matched && delta !== null ? (
        <div className={`mt-4 text-ink-soft ${text}`}>
          <p>
            Adding UAV imagery changed typical error by{' '}
            <span className="data font-medium text-ink">{signed(delta, 2)}</span> bu/ac (
            <span className="data">{uav!.satelliteOnly.mae.toFixed(2)}</span> →{' '}
            <span className="data">{uav!.satellitePlusUav.mae.toFixed(2)}</span>)
            {r2Delta !== null && (
              <>
                {' '}
                and R² by <span className="data font-medium text-ink">{signed(r2Delta, 3)}</span>
              </>
            )}
            .{uav!.note ? ` ${uav!.note}` : ''}
          </p>
          {!isPresentationMode && (
            <p className="mt-1 text-[12px] text-muted">
              Separate matched experiment
              {uav!.plots ? `: the same ${uav!.plots.toLocaleString('en-US')} plots` : ': the same plots'}
              {uav!.sites.length ? ` at ${uav!.sites.map(siteName).join(' and ')}` : ''}
              {uav!.dap != null ? `, about ${uav!.dap} days after planting` : ''}
              {uav!.validation ? `, ${uav!.validation}` : ''}
              {uav!.framework ? `. ${uav!.framework}` : ''}.
            </p>
          )}
        </div>
      ) : (
        <p className="mt-4 rounded-xl border border-dashed border-line-strong px-4 py-4 text-[13px] leading-relaxed text-muted">
          {uav && !uav.matched
            ? 'The published comparison is not a matched experiment, so it is not shown. '
            : 'Waiting for a matched comparison from the final run: the same plots, dates, validation split and model, with and without UAV. '}
          {uavSites.length > 0 &&
            `In the challenge data, UAV imagery exists for ${uavSites.map((s) => s.name).join(', ')} only, so the comparison can only be made there.`}
        </p>
      )}
    </section>
  );
}
