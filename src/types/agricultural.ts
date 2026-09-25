/**
 * Front-End Data Model Contract
 * The front end only consumes these normalized structures, whether they come from
 * the local demo data or, later, from the backend API that fronts the ML and
 * context services. Components never talk to external data providers directly.
 */

export type GrowthStage = 'Emergence' | 'Vegetative' | 'Reproductive' | 'Grain Fill' | 'Maturity';

export interface FieldMeta {
  id: string;
  name: string;
  crop: string;
  season: number;
  latitude: number;
  longitude: number;
  location: string;
  acreage: number;
  regionalBaseline: number; // bu/ac 5-year average
  soilClassification: string;
  irrigationStatus: 'Dryland' | 'Center Pivot' | 'Drip';
}

export interface WeatherContext {
  rainfall30Day: number; // mm
  rainfallComparison: number; // % delta vs 30-year normal (e.g. -31)
  rainfallStatus: 'deficit' | 'normal' | 'surplus';
  gddAccumulated: number; // Growing degree days
  gddComparison: number; // % delta
  heatExposureDays: number; // days > 95°F
  drySpellDays: number; // longest dry run this season
  updatedAgo: string; // e.g. "2 hours ago"
  avgTemperatureF: number;
  et0DemandMm: number; // Reference evapotranspiration
}

export interface SoilContext {
  awc: 'Low' | 'Moderate' | 'High';
  drainage: string; // e.g. "Well drained", "Somewhat poorly drained"
  organicMatter: number; // % (e.g. 3.1)
  ph: number; // e.g. 6.4
  dominantTexture: string; // e.g. "Silt loam"
  cationExchangeCapacity?: number; // meq/100g; not every source reports it
  rootZoneDepthCm: number;
  source: string; // "USDA NRCS SSURGO"
}

export interface ModelExplanation {
  id: string;
  title: string;
  influence: 'positive' | 'negative' | 'neutral';
  influenceLabel: 'Positive influence' | 'Negative influence' | 'Neutral / buffering influence';
  description: string;
  metricReference?: string;
}

export interface FeatureImportanceItem {
  name: string;
  weight: number; // percentage (0 - 100)
  category: 'Vegetation' | 'Weather' | 'Soil' | 'Temporal' | 'Management' | 'History';
  direction: 'positive' | 'negative' | 'neutral';
}

export interface SpatialZone {
  id: string;
  name: string; // "Zone 1", etc.
  gridRow: number;
  gridCol: number;
  predictedYield: number; // bu/ac
  ndvi: number;
  rainfall30Day: number; // mm
  soil: string;
  heatStressIndex: number; // 0.0 - 1.0
  satelliteReflectance: number; // 0.0 - 1.0
}

export interface SpatialContext {
  zones: SpatialZone[];
  resolutionMeters: number;
  tileDate: string;
  satellitePlatform: string;
  bounds: {
    north: number;
    south: number;
    east: number;
    west: number;
  };
  /** What the 16 cells are, e.g. "16 neighbouring trial plots, each forecast by the model". */
  description?: string;
  /** 'model': every cell comes from data or the model; 'illustrative': demo layer. */
  provenance?: 'illustrative' | 'model';
}

export interface ForecastSnapshot {
  id: string;
  date: string; // '2026-05-30', '2026-07-22', etc.
  displayDate: string; // 'May 30', 'Jul 22'
  stage: GrowthStage;
  stageSubtext: string; // e.g., 'V6 - Rapid vegetative growth', 'R1 - Silking / Pollination'
  yield: number; // bu/ac
  unit: string;
  lowerBound: number;
  upperBound: number;
  confidence: number; // percentage 0 - 100
  confidenceRating: 'LOW' | 'MODERATE' | 'HIGH';
  generatedAt: string;
  weather: WeatherContext;
  soil: SoilContext;
  explanations: ModelExplanation[];
  featureImportance: FeatureImportanceItem[];
  /** Absent before the first crop image: there is nothing to map yet. */
  spatial?: SpatialContext;
}

export interface EventMarker {
  date: string; // '2026-07-22'
  displayDate: string; // 'Jul 22'
  title: string;
  type: 'rain' | 'heat' | 'dry' | 'management' | 'recovery';
  summary: string;
  hoverDetail: string; // e.g. "High-temperature exposure: 4 days above 95°F during previous 10 days"
}

export interface VegetationObservation {
  date: string;
  displayDate: string;
  ndvi: number;
  ndre: number;
  regionalBaselineNdvi: number; // demo: 5-yr regional curve; API: same-day mean of the site's plots
  gndvi?: number;
  evi?: number;
  isForecastDatePoint?: boolean;
}

export interface HistoricalContext {
  regional5YearAvg: number;
  regionalDeltaPct: number;
  yearlyYields: Array<{
    year: number;
    yield: number;
    type: 'historical' | 'forecast';
  }>;
}

/**
 * `challenge` sources are provided by the hackathon. `public` sources are
 * government datasets SoilSignal already pulls in for each field's location.
 * `candidate` sources are possible enrichments that are not connected yet.
 */
export type SourceRole = 'challenge' | 'practice' | 'public' | 'model' | 'candidate';

export interface DataSource {
  id: string;
  name: string; // e.g. "Competition multispectral observations"
  shortName: string; // e.g. "Hackathon data", "PRISM / NOAA"
  purpose: string; // e.g. "Crop observations", "Weather"
  role: SourceRole;
  statusLabel: string; // e.g. "Challenge-provided", "Candidate weather enrichment"
  detail: string;
}

export interface FieldForecast {
  field: FieldMeta;
  storyDescription: string;
  snapshots: ForecastSnapshot[];
  fullVegetationSeries: VegetationObservation[];
  vegetationTimeline?: VegetationObservation[];
  events: EventMarker[];
  historical: HistoricalContext;
  sources: DataSource[];
  spatial?: SpatialContext;
  featureImportance?: FeatureImportanceItem[];
  metadata?: {
    forecastGeneratedAt: string;
    datasetVersion: string;
    lastSatellitePass?: string;
  };
}

// ---- Location context: public data for a field's coordinates ----------------
// Served by /api/context/*. Mirrors backend/app/schemas.py. Values come from USDA
// and NOAA services, normalized by the backend; `retrievedAt` is when it fetched them.

export interface County {
  name: string; // e.g. "Tippecanoe County"
  stateCode: string; // e.g. "IN"
  stateName: string;
  fips: string; // e.g. "18157"
}

export interface SoilProfile {
  mapUnitKey: string;
  mapUnitName: string; // e.g. "Chalmers silty clay loam"
  series: string; // dominant soil component, e.g. "Chalmers"
  componentPercent: number; // share of the map unit, 0-100
  taxonomicClass: string | null;
  texture: string | null; // surface horizon, e.g. "Silty clay loam"
  drainage: string | null; // e.g. "Poorly drained"
  hydrologicGroup: string | null; // e.g. "B/D"
  availableWaterCapacity: number | null; // cm of water per cm of soil, top 100 cm
  availableWaterStorageCm: number | null; // plant-available water in the top 100 cm
  availableWaterClass: 'Low' | 'Moderate' | 'High' | null;
  organicMatter: number | null; // %, surface horizon
  ph: number | null;
  rootZoneDepthCm: number | null;
  slopePercent: number | null;
  source: string; // "USDA NRCS SSURGO"
  retrievedAt: string;
}

export interface WeatherStation {
  id: string; // GHCN-Daily id, e.g. "USC00129430"
  name: string; // e.g. "West Lafayette 6 NW, IN"
  latitude: number;
  longitude: number;
  distanceKm: number;
}

export interface WeatherSummary {
  asOf: string; // ISO date the summary describes
  observedThrough: string | null; // last day with observations on or before asOf
  rainfallLast7DaysMm: number;
  rainfallLast30DaysMm: number;
  avgTempLast30DaysF: number | null;
  seasonStart: string; // ISO date season totals count from
  gddSinceSeasonStart: number; // growing degree days, base 50 °F, cap 86 °F
  heatDays: number; // days reaching 95 °F or more since season start
  longestDrySpellDays: number; // longest run of days under 1 mm of rain
  dataCompleteness: number; // 0-1
}

export interface ObservedWeather {
  station: WeatherStation;
  summaries: WeatherSummary[]; // one per requested date, in request order
  source: string; // "NOAA NCEI GHCN-Daily"
  retrievedAt: string;
}

export interface YieldHistory {
  county: County;
  years: Array<{ year: number; yield: number }>; // oldest first
  fiveYearAverage: number | null;
  unit: string; // "bu/ac"
  source: string; // "USDA NASS Quick Stats"
  retrievedAt: string;
}

/** One source's result. Sources fail independently, so each reports its own status. */
export interface ContextPart<T> {
  status: 'ok' | 'unavailable' | 'not_configured';
  data: T | null;
  message: string | null; // why the data is missing, in plain language
}

export interface LocationContext {
  latitude: number;
  longitude: number;
  county: County | null;
  soil: ContextPart<SoilProfile>;
  weather: ContextPart<ObservedWeather>;
  yieldHistory: ContextPart<YieldHistory>;
}
