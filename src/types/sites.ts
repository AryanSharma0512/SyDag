/**
 * Trial sites (GET /api/sites). Mirrors backend/app/sites.py.
 * The inventory part comes from the challenge data; `weather` and `forecasts` say what
 * this deployment can show for the site right now (absent in the demo build).
 */

export interface ImageryInventory {
  acquisitions: number; // passes or flights in the acquisition calendar
  acquisitionDates: string[];
  plotImages: number; // usable plot images in the challenge set; 0 = none at this site
  plotsImaged: number;
}

export interface TrialSeason {
  year: number;
  plantingDates: string[];
  plots: number;
  plotsWithYield: number;
  hybrids: number;
  satellite: ImageryInventory;
  uav: ImageryInventory;
}

export interface SiteWeather {
  librarySite: string; // the site's key for /api/weather-outlook
  seasons: number;
  firstSeason: number;
  lastSeason: number;
  station?: string;
  analogWeighting: boolean; // false: every historical season weighs the same
}

export interface SiteForecasts {
  livePlots: number; // plots the deployed models forecast
  finalPlots: number; // plots in the published final results
  finalSiteForecast: boolean;
  seasons: number[];
}

export interface TrialSite {
  id: string; // the data's spelling, e.g. "MOValley"
  name: string; // e.g. "Missouri Valley"
  state: string;
  stateName: string;
  latitude: number;
  longitude: number;
  coordinateSource: string;
  crop: string;
  irrigated: boolean;
  seasons: TrialSeason[];
  weather?: SiteWeather;
  forecasts?: SiteForecasts;
}
