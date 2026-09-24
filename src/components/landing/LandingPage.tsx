import React from 'react';
import { APP_CONFIG } from '../../config/appConfig';
import { ArrowRight, TrendingUp, ShieldCheck, Cpu, Database, ChevronRight } from 'lucide-react';

interface LandingPageProps {
  onNavigateToDashboard: () => void;
  onNavigateToAbout: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  onNavigateToDashboard,
  onNavigateToAbout,
}) => {
  return (
    <div className="min-h-[calc(100vh-60px)] flex flex-col justify-between bg-[#FBFBFA]">
      {/* Hero Section */}
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 text-center">
        {/* Subtle Dataset Chip */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono text-emerald-900 bg-emerald-50 border border-emerald-200/80 mb-6">
          <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse"></span>
          <span>{APP_CONFIG.datasetLabel} · Hackathon Front-End Shell</span>
        </div>

        {/* Hero Title */}
        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-slate-900 max-w-3xl mx-auto leading-tight">
          Predict yield earlier. <br className="hidden sm:inline" />
          <span className="text-emerald-800">Understand why.</span>
        </h1>

        {/* Supporting text */}
        <p className="mt-5 text-base sm:text-lg text-slate-600 max-w-2xl mx-auto leading-relaxed">
          Combine crop observations, environmental conditions, and agricultural context into progressive, explainable yield forecasts throughout the growing season.
        </p>

        {/* Primary CTA */}
        <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
          <button
            onClick={onNavigateToDashboard}
            className="w-full sm:w-auto px-6 py-3 bg-emerald-700 hover:bg-emerald-800 text-white font-medium rounded-md shadow-xs transition-colors flex items-center justify-center gap-2 text-sm cursor-pointer"
          >
            <span>Explore Dashboard</span>
            <ArrowRight className="w-4 h-4" />
          </button>

          <button
            onClick={onNavigateToAbout}
            className="w-full sm:w-auto px-5 py-3 bg-white hover:bg-slate-50 text-slate-700 font-medium rounded-md border border-slate-300 transition-colors flex items-center justify-center gap-1.5 text-sm cursor-pointer"
          >
            <span>Methodology & Data</span>
            <ChevronRight className="w-4 h-4 text-slate-400" />
          </button>
        </div>

        {/* Value-prop cards (Item 6 of brief) */}
        <div className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-6 text-left">
          {/* Card 1 */}
          <div className="p-6 rounded-lg bg-white border border-slate-200/80 shadow-xs hover:border-slate-300 transition-colors flex flex-col justify-between">
            <div>
              <div className="w-9 h-9 rounded bg-emerald-50 text-emerald-700 flex items-center justify-center mb-4">
                <TrendingUp className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900 tracking-tight mb-2">
                Progressive Forecasting
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Yield expectations update dynamically as new satellite, weather, and soil signals arrive, moving from broad regional climatology to high-confidence harvest projections.
              </p>
            </div>
            <div className="mt-5 pt-3 border-t border-slate-100 text-[11px] font-mono text-emerald-800">
              Scrub temporal trajectory →
            </div>
          </div>

          {/* Card 2 */}
          <div className="p-6 rounded-lg bg-white border border-slate-200/80 shadow-xs hover:border-slate-300 transition-colors flex flex-col justify-between">
            <div>
              <div className="w-9 h-9 rounded bg-blue-50 text-blue-700 flex items-center justify-center mb-4">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900 tracking-tight mb-2">
                Uncertainty Quantification
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Forecasts include explicit confidence ratings and 90% prediction intervals rather than single-number guesses, clearly reflecting in-season variance.
              </p>
            </div>
            <div className="mt-5 pt-3 border-t border-slate-100 text-[11px] font-mono text-blue-800">
              Calibrated spread bands →
            </div>
          </div>

          {/* Card 3 */}
          <div className="p-6 rounded-lg bg-white border border-slate-200/80 shadow-xs hover:border-slate-300 transition-colors flex flex-col justify-between">
            <div>
              <div className="w-9 h-9 rounded bg-amber-50 text-amber-700 flex items-center justify-center mb-4">
                <Cpu className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900 tracking-tight mb-2">
                Interpretable Agronomic Drivers
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Understand whether deviations are associated with canopy vigor, heat exposure, or moisture deficit using disciplined, non-causal feature importance attribution.
              </p>
            </div>
            <div className="mt-5 pt-3 border-t border-slate-100 text-[11px] font-mono text-amber-800">
              Sensor attribution signals →
            </div>
          </div>
        </div>
      </div>

      {/* Clean Minimal Footer */}
      <footer className="border-t border-slate-200/80 py-6 px-4 bg-white">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-800">{APP_CONFIG.name}</span>
            <span>—</span>
            <span>{APP_CONFIG.subtitle}</span>
          </div>
          <div className="font-mono text-[11px] text-slate-400">
            IoT4Ag Hackathon · Standalone Front-End Architecture
          </div>
        </div>
      </footer>
    </div>
  );
};
