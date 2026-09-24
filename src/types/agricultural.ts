/**
 * Front-End Data Model Contract
 * Standardized typed structures matching Section 28 of the Developer Brief.
 * The front-end only consumes this clean contract regardless of whether it originates
 * from mock state or future real backend / ML services.
 */

export type GrowthStage = 'Emergence' | 'Vegetative' | 'Reproductive' | 'Maturity';

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
  cationExchangeCapacity: number; // meq/100g
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
  category: 'Vegetation' | 'Weather' | 'Soil' | 'Temporal';
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
  spatial: SpatialContext;
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
  regionalBaselineNdvi: number;
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

export interface DataSource {
  id: string;
  name: string;
  source: string;
  resolution: string;
  lastObservation: string;
  status: 'active' | 'degraded' | 'cached';
  badge: string;
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
