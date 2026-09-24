import React, { useState } from 'react';
import { WeatherContext, SoilContext } from '../../types/agricultural';
import { CloudRain, Sun, Thermometer, Droplets, Layers, ShieldAlert, ArrowDown, ArrowUp, Minus } from 'lucide-react';

interface EnvironmentalContextProps {
  weather: WeatherContext;
  soil: SoilContext;
}

export const EnvironmentalContext: React.FC<EnvironmentalContextProps> = ({ weather, soil }) => {
  const [activeTab, setActiveTab] = useState<'weather' | 'soil'>('weather');

  return (
    <div className="bg-white border border-slate-200/90 rounded-lg p-5 shadow-xs transition-all h-full flex flex-col justify-between">
      <div>
        {/* Header & Tabs */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div>
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">
              Environmental Context
            </h3>
            <p className="text-[11px] text-slate-600">
              {activeTab === 'weather'
                ? 'Atmospheric conditions & moisture balance'
                : 'Pedological survey & hydraulic properties'}
            </p>
          </div>

          <div className="flex items-center gap-1 p-0.5 bg-slate-100/90 rounded border border-slate-200/60">
            <button
              onClick={() => setActiveTab('weather')}
              className={`px-3 py-1 text-xs font-medium rounded transition-all cursor-pointer ${
                activeTab === 'weather'
                  ? 'bg-white text-emerald-950 font-bold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Weather
            </button>
            <button
              onClick={() => setActiveTab('soil')}
              className={`px-3 py-1 text-xs font-medium rounded transition-all cursor-pointer ${
                activeTab === 'soil'
                  ? 'bg-white text-emerald-950 font-bold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Soil
            </button>
          </div>
        </div>

        {/* Tab 1: Weather View (Compact rows inside one context panel) */}
        {activeTab === 'weather' && (
          <div className="mt-3.5 space-y-2.5">
            {/* Row 1: Rainfall */}
            <div className="flex items-center justify-between p-2.5 rounded border border-slate-100 hover:border-slate-200 bg-[#FBFBFA] transition-colors">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded bg-blue-50 text-blue-800 flex items-center justify-center shrink-0">
                  <CloudRain className="w-4 h-4" />
                </div>
                <div>
                  <span className="text-xs font-semibold text-slate-800 block">Rainfall</span>
                  <span className="text-[11px] text-slate-600 font-mono">30-day cumulative</span>
                </div>
              </div>

              <div className="text-right">
                <div className="flex items-baseline justify-end gap-1 font-mono">
                  <span className="text-base font-bold text-slate-900">{weather.rainfall30Day}</span>
                  <span className="text-xs text-slate-600">mm</span>
                </div>
                <div className="flex items-center justify-end gap-0.5 text-[11px] font-mono">
                  {weather.rainfallComparison < 0 ? (
                    <>
                      <ArrowDown className="w-3 h-3 text-amber-800" />
                      <span className="text-amber-800 font-medium">
                        {Math.abs(weather.rainfallComparison)}% vs normal
                      </span>
                    </>
                  ) : weather.rainfallComparison > 0 ? (
                    <>
                      <ArrowUp className="w-3 h-3 text-blue-800" />
                      <span className="text-blue-800 font-medium">
                        +{weather.rainfallComparison}% vs normal
                      </span>
                    </>
                  ) : (
                    <>
                      <Minus className="w-3 h-3 text-slate-600" />
                      <span className="text-slate-600 font-medium">Normal</span>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Row 2: Growing Degree Days */}
            <div className="flex items-center justify-between p-2.5 rounded border border-slate-100 hover:border-slate-200 bg-[#FBFBFA] transition-colors">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded bg-amber-50 text-amber-800 flex items-center justify-center shrink-0">
                  <Sun className="w-4 h-4" />
                </div>
                <div>
                  <span className="text-xs font-semibold text-slate-800 block">Growing Degree Days</span>
                  <span className="text-[11px] text-slate-600 font-mono">Base 50°F / 86°F ceiling</span>
                </div>
              </div>

              <div className="text-right">
                <div className="flex items-baseline justify-end gap-1 font-mono">
                  <span className="text-base font-bold text-slate-900">
                    {weather.gddAccumulated.toLocaleString()}
                  </span>
                  <span className="text-xs text-slate-600">GDD</span>
                </div>
                <span className="text-[11px] font-mono text-slate-600 block">
                  {weather.gddComparison >= 0 ? `+${weather.gddComparison}%` : `${weather.gddComparison}%`} vs 10-yr pace
                </span>
              </div>
            </div>

            {/* Row 3: Heat Exposure */}
            <div className="flex items-center justify-between p-2.5 rounded border border-slate-100 hover:border-slate-200 bg-[#FBFBFA] transition-colors">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded bg-rose-50 text-rose-800 flex items-center justify-center shrink-0">
                  <Thermometer className="w-4 h-4" />
                </div>
                <div>
                  <span className="text-xs font-semibold text-slate-800 block">Heat Exposure</span>
                  <span className="text-[11px] text-slate-600 font-mono">Above critical threshold</span>
                </div>
              </div>

              <div className="text-right">
                <div className="flex items-baseline justify-end gap-1 font-mono">
                  <span className="text-base font-bold text-slate-900">
                    {weather.heatExposureDays}
                  </span>
                  <span className="text-xs text-slate-600">days</span>
                </div>
                <span className="text-[11px] font-mono text-slate-600 block">above 95°F</span>
              </div>
            </div>

            {/* Row 4: Dry Spell */}
            <div className="flex items-center justify-between p-2.5 rounded border border-slate-100 hover:border-slate-200 bg-[#FBFBFA] transition-colors">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded bg-emerald-50 text-emerald-800 flex items-center justify-center shrink-0">
                  <Droplets className="w-4 h-4" />
                </div>
                <div>
                  <span className="text-xs font-semibold text-slate-800 block">Dry Spell</span>
                  <span className="text-[11px] text-slate-600 font-mono">Longest run this season</span>
                </div>
              </div>

              <div className="text-right">
                <div className="flex items-baseline justify-end gap-1 font-mono">
                  <span className="text-base font-bold text-slate-900">
                    {weather.drySpellDays}
                  </span>
                  <span className="text-xs text-slate-600">days</span>
                </div>
                <span className="text-[11px] font-mono text-slate-600 block">zero precip run</span>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Soil View */}
        {activeTab === 'soil' && (
          <div className="mt-3.5 space-y-2.5">
            {/* AWC */}
            <div className="flex items-center justify-between p-2.5 rounded border border-slate-100 hover:border-slate-200 bg-[#FBFBFA] transition-colors">
              <div>
                <span className="text-xs font-semibold text-slate-800 block">Available Water Capacity</span>
                <span className="text-[11px] text-slate-600 font-mono">Top 150 cm profile buffer</span>
              </div>
              <span className="text-xs font-semibold font-mono text-emerald-950 px-2 py-0.5 bg-emerald-50 border border-emerald-200/60 rounded">
                {soil.awc}
              </span>
            </div>

            {/* Drainage */}
            <div className="flex items-center justify-between p-2.5 rounded border border-slate-100 hover:border-slate-200 bg-[#FBFBFA] transition-colors">
              <div>
                <span className="text-xs font-semibold text-slate-800 block">Drainage Class</span>
                <span className="text-[11px] text-slate-600 font-mono">Hydrologic natural classification</span>
              </div>
              <span className="text-xs font-medium text-slate-800 font-mono">
                {soil.drainage}
              </span>
            </div>

            {/* Organic Matter & pH */}
            <div className="grid grid-cols-2 gap-2">
              <div className="p-2.5 rounded border border-slate-100 bg-[#FBFBFA]">
                <span className="text-[11px] text-slate-600 block">Organic Matter</span>
                <span className="text-sm font-bold font-mono text-slate-900">
                  {soil.organicMatter}%
                </span>
              </div>
              <div className="p-2.5 rounded border border-slate-100 bg-[#FBFBFA]">
                <span className="text-[11px] text-slate-600 block">Soil pH</span>
                <span className="text-sm font-bold font-mono text-slate-900">
                  {soil.ph}
                </span>
              </div>
            </div>

            {/* Dominant Texture */}
            <div className="flex items-center justify-between p-2.5 rounded border border-slate-100 hover:border-slate-200 bg-[#FBFBFA] transition-colors">
              <div>
                <span className="text-xs font-semibold text-slate-800 block">Dominant Texture</span>
                <span className="text-[11px] text-slate-600 font-mono">Particle distribution</span>
              </div>
              <span className="text-xs font-medium text-slate-800 font-mono">
                {soil.dominantTexture}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Subtle Source Attribution */}
      <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-600 font-mono">
        <span>
          Source: {activeTab === 'weather' ? 'PRISM / NOAA HRRR' : soil.source}
        </span>
        <span className="text-slate-600">Updated {weather.updatedAgo}</span>
      </div>
    </div>
  );
};
