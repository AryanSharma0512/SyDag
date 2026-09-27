import { useMemo, useState } from 'react';

type TrialSite = {
  id: string;
  name: string;
  state: string;
  latitude: number;
  longitude: number;
};

const SITES: TrialSite[] = [
  { id: 'ames', name: 'Ames', state: 'IA', latitude: 42.014713, longitude: -93.732245 },
  { id: 'crawfordsville', name: 'Crawfordsville', state: 'IA', latitude: 41.198935, longitude: -91.486866 },
  { id: 'lincoln', name: 'Lincoln', state: 'NE', latitude: 40.8522, longitude: -96.615341 },
  { id: 'missouri-valley', name: 'Missouri Valley', state: 'IA', latitude: 41.671, longitude: -95.942 },
  { id: 'scottsbluff', name: 'Scottsbluff', state: 'NE', latitude: 41.95, longitude: -103.703 },
];

const project = (longitude: number, latitude: number) => ({
  x: 72 + ((longitude + 125) / 59) * 816,
  y: 72 + ((49 - latitude) / 25) * 340,
});

/**
 * Presentation-first map of the five research locations. The outline is intentionally
 * subdued; the data locations carry the emphasis.
 */
export function TrialSiteMap() {
  const [selectedId, setSelectedId] = useState('ames');
  const selected = SITES.find((site) => site.id === selectedId) ?? SITES[0];
  const points = useMemo(
    () => SITES.map((site) => ({ ...site, ...project(site.longitude, site.latitude) })),
    [],
  );

  return (
    <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20" aria-labelledby="trial-map-heading">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1.45fr)_minmax(18rem,0.55fr)] lg:items-center">
        <div>
          <p className="text-[13px] font-medium text-leaf-700">Five trial locations</p>
          <h2 id="trial-map-heading" className="mt-3 text-[28px] font-semibold tracking-[-0.025em] text-ink sm:text-[36px]">
            One model, tested across different growing environments.
          </h2>
          <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted">
            Select a location to see where the maize trials were grown. Final forecast results will plug into the same
            site structure once the model team freezes tonight&apos;s outputs.
          </p>

          <div className="mt-7 rounded-2xl border border-line bg-surface p-3 sm:p-5">
            <svg viewBox="0 0 960 500" role="img" aria-label="Map of the contiguous United States with five maize trial locations" className="h-auto w-full">
              <path
                d="M78 112 L132 88 L222 77 L298 83 L360 71 L431 82 L504 70 L583 83 L647 76 L705 91 L771 91 L836 118 L882 151 L872 181 L834 194 L844 221 L817 249 L793 286 L774 330 L740 343 L714 320 L686 335 L657 331 L626 348 L582 350 L546 364 L496 361 L457 379 L411 371 L372 387 L328 372 L296 347 L262 347 L232 323 L195 321 L171 292 L139 282 L121 248 L103 228 L106 194 L89 168 Z"
                className="fill-mist stroke-line-strong"
                strokeWidth="2"
              />
              <path
                d="M738 343 L758 365 L767 399 L786 431 L775 443 L756 423 L748 390 L728 365 Z"
                className="fill-mist stroke-line-strong"
                strokeWidth="2"
              />
              {points.map((site) => {
                const active = site.id === selected.id;
                return (
                  <g
                    key={site.id}
                    role="button"
                    tabIndex={0}
                    aria-label={`Select ${site.name}, ${site.state}`}
                    onClick={() => setSelectedId(site.id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        setSelectedId(site.id);
                      }
                    }}
                    className="cursor-pointer outline-none"
                  >
                    <circle cx={site.x} cy={site.y} r={active ? 13 : 10} className="fill-leaf-100/80" />
                    <circle cx={site.x} cy={site.y} r={active ? 6 : 4.5} className="fill-leaf-700" />
                    <title>{site.name}, {site.state}</title>
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        <aside className="rounded-2xl border border-line bg-surface p-6" aria-live="polite">
          <p className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">Selected trial</p>
          <h3 className="mt-3 text-[26px] font-semibold tracking-[-0.025em] text-ink">{selected.name}</h3>
          <p className="mt-1 text-[15px] text-muted">{selected.state === 'IA' ? 'Iowa' : 'Nebraska'}</p>

          <dl className="mt-6 space-y-4 border-t border-line pt-5 text-[14px]">
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-muted">Crop</dt>
              <dd className="font-medium text-ink">Maize</dd>
            </div>
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-muted">Trial season</dt>
              <dd className="data font-medium text-ink">2022</dd>
            </div>
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-muted">Core imagery</dt>
              <dd className="font-medium text-ink">Satellite</dd>
            </div>
          </dl>

          <p className="mt-6 text-[13px] leading-relaxed text-muted">
            Site-level forecast values will come from the frozen model-results file rather than being typed into the UI.
          </p>
        </aside>
      </div>
    </section>
  );
}
