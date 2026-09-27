import { useEffect, useState } from 'react';
import { CloudSun, ClipboardList, Plane, Satellite } from 'lucide-react';
import type { TrialSite } from '../../types/sites';
import { getTrialSites, isMappable } from '../../services/sites';
import { formatDay, formatNumber } from '../../utils/formatters';

const range = (dates: string[]) =>
  dates.length === 0
    ? '—'
    : dates.length === 1
      ? formatDay(dates[0])
      : `${formatDay(dates[0])}–${formatDay(dates[dates.length - 1])}`;

/**
 * The challenge data behind the forecasts, by location, from GET /api/sites (the
 * challenge inventory). In the order that matters for the product: satellite imagery
 * first, then weather, the field records, and the optional UAV imagery.
 */
export function TrialDataSection() {
  const [sites, setSites] = useState<TrialSite[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    getTrialSites()
      .then((list) => active && setSites(list.filter(isMappable)))
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
    };
  }, []);

  const rows = (sites ?? []).flatMap((site) => site.seasons.map((season) => ({ site, season })));
  const imaged = rows.filter((r) => r.season.satellite.plotImages > 0);
  const uav = rows.filter((r) => r.season.uav.plotImages > 0);
  const passDates = imaged.flatMap((r) => r.season.satellite.acquisitionDates).sort();
  const weatherSeasons = (sites ?? []).flatMap((s) => (s.weather ? [s.weather.seasons] : []));
  const plots = rows.reduce((n, r) => n + r.season.plots, 0);
  const scheduledOnly = rows.filter((r) => r.season.satellite.acquisitions > 0 && r.season.satellite.plotImages === 0);

  const cards = [
    {
      icon: Satellite,
      title: 'Satellite imagery',
      tag: 'Base layer',
      body: imaged.length
        ? `Pléiades Neo, six bands (red, green, blue, near infrared, red edge, deep blue), clipped to each plot. ${formatNumber(
            imaged.reduce((n, r) => n + r.season.satellite.plotImages, 0),
          )} plot images at ${imaged.map((r) => r.site.name).join(', ')}, ${range([passDates[0], passDates[passDates.length - 1]].filter(Boolean))}.`
        : 'Six-band Pléiades Neo plot images.',
    },
    {
      icon: CloudSun,
      title: 'Weather',
      tag: 'Every site',
      body: weatherSeasons.length
        ? `Daily station weather through the season, plus ${Math.min(...weatherSeasons)}–${Math.max(...weatherSeasons)} quality-checked past seasons per site from NOAA GHCN-Daily for the historical outlook.`
        : 'Daily station weather through the season, and NOAA station history for the outlook.',
    },
    {
      icon: ClipboardList,
      title: 'Field records',
      tag: 'Every plot',
      body: `Hybrid, nitrogen rate, irrigation and planting date for ${formatNumber(plots)} trial plots: what a grower already knows at planting.`,
    },
    {
      icon: Plane,
      title: 'UAV imagery',
      tag: 'Optional',
      body: uav.length
        ? `Uncalibrated RGB drone images at ${uav.map((r) => r.site.name).join(', ')} only (${uav
            .map((r) => `${r.season.uav.acquisitions} flights, ${formatNumber(r.season.uav.plotImages)} plot images`)
            .join('; ')}). Used to test whether an extra flight adds enough to pay for.`
        : 'Drone imagery, where collected. Used to test whether an extra flight adds enough to pay for.',
    },
  ];

  return (
    <section aria-labelledby="trial-data-heading">
      <h2 id="trial-data-heading" className="text-[22px] font-semibold tracking-[-0.02em] text-ink">
        Trial data
      </h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
        The challenge data behind the forecasts: maize trial plots with harvested yields, and what was observed at each location.
      </p>

      <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(({ icon: Icon, title, tag, body }) => (
          <li key={title} className="rounded-2xl border border-line bg-surface p-5">
            <div className="flex items-center justify-between gap-2">
              <Icon className="h-5 w-5 text-leaf-700" aria-hidden="true" />
              <span className="rounded-full bg-mist px-2 py-0.5 text-[11px] font-medium text-muted">{tag}</span>
            </div>
            <h3 className="mt-3 text-[16px] font-semibold tracking-[-0.01em] text-ink">{title}</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{body}</p>
          </li>
        ))}
      </ul>

      <div className="mt-8 overflow-x-auto">
        {failed ? (
          <p className="text-[14px] text-muted">The trial inventory could not be loaded.</p>
        ) : !sites ? (
          <div className="ss-skeleton h-48 rounded-lg" aria-busy="true" />
        ) : (
          <table className="w-full min-w-[760px] text-left">
            <caption className="sr-only">Trial data by location</caption>
            <thead>
              <tr className="border-b border-line-strong text-[13px] text-muted">
                <th scope="col" className="py-2.5 pr-4 font-medium">
                  Location
                </th>
                <th scope="col" className="py-2.5 pr-4 font-medium">
                  Season
                </th>
                <th scope="col" className="py-2.5 pr-4 text-right font-medium">
                  Plots with yield
                </th>
                <th scope="col" className="py-2.5 pr-4 text-right font-medium">
                  Hybrids
                </th>
                <th scope="col" className="py-2.5 pr-4 font-medium">
                  Planted
                </th>
                <th scope="col" className="py-2.5 pr-4 font-medium">
                  Satellite
                </th>
                <th scope="col" className="py-2.5 pr-4 font-medium">
                  UAV
                </th>
                <th scope="col" className="py-2.5 font-medium">
                  Weather history
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ site, season }) => (
                <tr key={`${site.id}-${season.year}`} className="border-b border-line text-[14px]">
                  <td className="py-3 pr-4 font-medium text-ink">
                    {site.name} <span className="font-normal text-faint">{site.state}</span>
                    {site.irrigated && <span className="ml-2 text-[12px] font-normal text-muted">irrigated</span>}
                  </td>
                  <td className="data py-3 pr-4 text-ink-soft">{season.year}</td>
                  <td className="data py-3 pr-4 text-right text-ink-soft">{formatNumber(season.plotsWithYield)}</td>
                  <td className="data py-3 pr-4 text-right text-ink-soft">{season.hybrids}</td>
                  <td className="data py-3 pr-4 text-ink-soft">{range(season.plantingDates)}</td>
                  <td className="py-3 pr-4 text-ink-soft">
                    {season.satellite.plotImages > 0 ? (
                      <>
                        <span className="data">{season.satellite.acquisitions}</span> passes ·{' '}
                        <span className="data">{formatNumber(season.satellite.plotImages)}</span> images
                      </>
                    ) : (
                      <span className="text-faint">No plot images</span>
                    )}
                  </td>
                  <td className="py-3 pr-4 text-ink-soft">
                    {season.uav.plotImages > 0 ? (
                      <>
                        <span className="data">{season.uav.acquisitions}</span> flights ·{' '}
                        <span className="data">{formatNumber(season.uav.plotImages)}</span> images
                      </>
                    ) : (
                      <span className="text-faint">—</span>
                    )}
                  </td>
                  <td className="py-3 text-ink-soft">
                    {site.weather ? (
                      <>
                        <span className="data">{site.weather.seasons}</span> seasons
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="mt-3 text-[12px] leading-relaxed text-muted">
        Plot images are the usable images in the challenge data.
        {scheduledOnly.length > 0 &&
          ` ${scheduledOnly.map((r) => r.site.name).join(' and ')} had satellite passes scheduled but no plot images, so forecasts there can rest only on field records and weather.`}
      </p>
    </section>
  );
}
