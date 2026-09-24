import React from 'react';
import { APP_CONFIG } from '../../config/appConfig';
import { Database, Layers, ShieldCheck, Cpu, ArrowLeft, ExternalLink, Calendar, CheckCircle2 } from 'lucide-react';

interface AboutPageProps {
  onNavigateToDashboard: () => void;
}

export const AboutPage: React.FC<AboutPageProps> = ({ onNavigateToDashboard }) => {
  return (
    <div className="min-h-screen bg-[#FBFBFA] py-10 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Back Link */}
        <div>
          <button
            onClick={onNavigateToDashboard}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-800 hover:text-emerald-950 transition-colors cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Return to Dashboard</span>
          </button>
        </div>

        {/* Title Header */}
        <div className="border-b border-slate-200 pb-6">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded text-xs font-mono text-emerald-800 bg-emerald-50 border border-emerald-200/80 mb-3">
            <span>Methodology & Agronomic Intelligence Architecture</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">
            Forecasting Framework & Data Sources
          </h1>
          <p className="mt-2 text-sm text-slate-600 leading-relaxed">
            How {APP_CONFIG.name} fuses multispectral observations, weather reanalysis, pedological surveys, and historical yield distributions into progressive, calibrated maize yield predictions.
          </p>
        </div>

        {/* Section 1: Progressive Forecasting Concept */}
        <section className="bg-white rounded-lg border border-slate-200/80 p-6 shadow-xs space-y-3">
          <div className="flex items-center gap-2 text-slate-900 font-bold text-base">
            <Cpu className="w-5 h-5 text-emerald-700" />
            <h2>Progressive In-Season Forecasting</h2>
          </div>
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Conventional crop yield models often operate either as post-season hindcasts or produce static mid-summer point estimates with unquantified uncertainty. {APP_CONFIG.name} treats yield forecasting as a dynamic state-space process: as each weekly satellite pass and meteorological update becomes available, the model refines its expected yield distribution.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
            <div className="p-3 bg-[#FBFBFA] rounded border border-slate-200/60 text-xs">
              <span className="font-bold text-slate-900 block mb-1">1. Early Season (May–Jun)</span>
              <span className="text-slate-600">
                Dominated by soil available water capacity (AWC), historical county baselines, and emergence temperatures. Wide 90% prediction spread.
              </span>
            </div>
            <div className="p-3 bg-[#FBFBFA] rounded border border-slate-200/60 text-xs">
              <span className="font-bold text-slate-900 block mb-1">2. Mid Season (Jul)</span>
              <span className="text-slate-600">
                Peak vegetative vigor (NDVI/NDRE), silking heat stress, and 30-day precipitation balance. Uncertainty narrows rapidly.
              </span>
            </div>
            <div className="p-3 bg-[#FBFBFA] rounded border border-slate-200/60 text-xs">
              <span className="font-bold text-slate-900 block mb-1">3. Late Season (Aug–Sep)</span>
              <span className="text-slate-600">
                Canopy senescence rates, grain fill degree-days, and dry-down telemetry. High confidence consensus (85%+).
              </span>
            </div>
          </div>
        </section>

        {/* Section 2: Uncertainty Quantification */}
        <section className="bg-white rounded-lg border border-slate-200/80 p-6 shadow-xs space-y-3">
          <div className="flex items-center gap-2 text-slate-900 font-bold text-base">
            <ShieldCheck className="w-5 h-5 text-emerald-700" />
            <h2>Uncertainty Quantification & Prediction Intervals</h2>
          </div>
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Rather than producing single deterministic point forecasts that mislead growers, {APP_CONFIG.name} outputs a calibrated 90% prediction interval (5th to 95th percentile).
          </p>
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Confidence scores represent ensemble concordance across spatial and temporal features. If weather forecasts diverge or satellite coverage suffers from cloud occlusion, the interval expands and the confidence rating drops to MODERATE or LOW, maintaining empirical honesty.
          </p>
        </section>

        {/* Section 3: Data Provenance & Pipeline Integration */}
        <section className="bg-white rounded-lg border border-slate-200/80 p-6 shadow-xs space-y-4">
          <div className="flex items-center gap-2 text-slate-900 font-bold text-base">
            <Database className="w-5 h-5 text-emerald-700" />
            <h2>Data Sources & Provenance</h2>
          </div>
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            When deployed against live competition data, {APP_CONFIG.name} connects directly to five authoritative agro-environmental feeds:
          </p>

          <div className="space-y-3">
            <div className="p-3.5 rounded border border-slate-200 bg-[#FBFBFA] flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <span className="font-bold text-slate-900 text-xs block">
                  IoT4Ag Hackathon Multispectral Observations
                </span>
                <span className="text-xs text-slate-600">
                  Calibrated field-level spectral reflectance indices (NDVI, NDRE) for experimental plots.
                </span>
              </div>
              <span className="text-[11px] font-mono text-slate-500 shrink-0">Cadence: 5-7 days</span>
            </div>

            <div className="p-3.5 rounded border border-slate-200 bg-[#FBFBFA] flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <span className="font-bold text-slate-900 text-xs block">
                  PRISM Climate Group & NOAA HRRR
                </span>
                <span className="text-xs text-slate-600">
                  Daily precipitation accumulation, maximum/minimum temperature grids, and GDD base 50°F.
                </span>
              </div>
              <span className="text-[11px] font-mono text-slate-500 shrink-0">Daily 4km / Hourly 3km</span>
            </div>

            <div className="p-3.5 rounded border border-slate-200 bg-[#FBFBFA] flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <span className="font-bold text-slate-900 text-xs block">
                  USDA NRCS Soil Survey Geographic Database (SSURGO)
                </span>
                <span className="text-xs text-slate-600">
                  High-resolution soil pedon properties: Available Water Capacity (AWC), drainage class, organic matter, and pH.
                </span>
              </div>
              <span className="text-[11px] font-mono text-slate-500 shrink-0">Static 1:24,000</span>
            </div>

            <div className="p-3.5 rounded border border-slate-200 bg-[#FBFBFA] flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <span className="font-bold text-slate-900 text-xs block">
                  USDA NASS Quick Stats (National Agricultural Statistics Service)
                </span>
                <span className="text-xs text-slate-600">
                  10-year county-level historical yield baselines for regional anomaly normalization.
                </span>
              </div>
              <span className="text-[11px] font-mono text-slate-500 shrink-0">Annual County Census</span>
            </div>

            <div className="p-3.5 rounded border border-slate-200 bg-[#FBFBFA] flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <span className="font-bold text-slate-900 text-xs block">
                  Copernicus Sentinel-2 MSI Level-2A
                </span>
                <span className="text-xs text-slate-600">
                  10-meter bottom-of-atmosphere surface reflectance for intra-field spatial variability zoning.
                </span>
              </div>
              <span className="text-[11px] font-mono text-slate-500 shrink-0">5-day revisit</span>
            </div>
          </div>
        </section>

        {/* Bottom CTA */}
        <div className="text-center pt-4">
          <button
            onClick={onNavigateToDashboard}
            className="px-6 py-2.5 bg-emerald-700 hover:bg-emerald-800 text-white font-medium rounded-md text-sm transition-colors cursor-pointer"
          >
            Launch Interactive Yield Dashboard
          </button>
        </div>
      </div>
    </div>
  );
};
