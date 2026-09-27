/**
 * Trial Sites Service
 * The trial locations for the map and the dashboard's location selector.
 * GET /api/sites in API mode. The demo build uses the generated snapshot of the same
 * list (no forecasts at any of them) plus one "Demo fields" location for its own data.
 */

import type { TrialSite, TrialSeason } from '../types/sites';
import { APP_CONFIG } from '../config/appConfig';
import { TRIAL_SITES } from '../mock/trialSites';
import { apiGet } from './apiClient';
import { demoSite } from './plotForecasts';

let request: Promise<TrialSite[]> | null = null;

export function getTrialSites(): Promise<TrialSite[]> {
  if (APP_CONFIG.demoMode) return Promise.resolve([...TRIAL_SITES, demoSite()]);
  if (!request) {
    request = apiGet<TrialSite[]>('/sites').catch((err: unknown) => {
      request = null;
      throw err;
    });
  }
  return request;
}

export function findSite(sites: TrialSite[], idOrName: string | null | undefined): TrialSite | undefined {
  if (!idOrName) return undefined;
  const key = idOrName.toLowerCase();
  return sites.find((s) => s.id.toLowerCase() === key || s.name.toLowerCase() === key);
}

export function siteLabel(site: TrialSite): string {
  return site.state ? `${site.name}, ${site.stateName}` : site.name;
}

/** Sites that belong on the map: trial sites with real coordinates. */
export function isMappable(site: TrialSite): boolean {
  return site.coordinateSource !== 'demo';
}

export function seasonFor(site: TrialSite, year: number | undefined): TrialSeason | undefined {
  return site.seasons.find((s) => s.year === year) ?? site.seasons[0];
}

/** True when this deployment can show plot forecasts for the site. */
export function hasForecasts(site: TrialSite): boolean {
  const f = site.forecasts;
  return !!f && (f.livePlots > 0 || f.finalPlots > 0 || f.finalSiteForecast);
}
