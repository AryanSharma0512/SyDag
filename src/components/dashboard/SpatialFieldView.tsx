import React, { useState } from 'react';
import { SpatialContext, SpatialZone } from '../../types/agricultural';
import { Layers, Crosshair, MapPin, Eye, Satellite, HelpCircle } from 'lucide-react';

interface SpatialFieldViewProps {
  spatial?: SpatialContext;
  fieldName: string;
}

export const SpatialFieldView: React.FC<SpatialFieldViewProps> = ({
  spatial,
  fieldName,
}) => {
  const [activeLayer, setActiveLayer] = useState<'satellite' | 'vegetation' | 'yield'>('vegetation');
  const [hoveredZone, setHoveredZone] = useState<SpatialZone | null>(
    spatial?.zones[13] || null // Default to Zone 14 (index 13) matching brief example
  );

  const zones = spatial?.zones || [];

  // Helper to color each zone based on the active layer
  const getZoneStyle = (z: SpatialZone) => {
    if (activeLayer === 'satellite') {
      // Natural agricultural surface tones
      const alpha = 0.5 + z.satelliteReflectance * 0.4;
      return {
        backgroundColor: `rgba(47, 85, 54, ${alpha})`,
        border: '1px solid rgba(255, 255, 255, 0.15)',
      };
    } else if (activeLayer === 'vegetation') {
      // NDVI colormap (from 0.35 yellow-green to 0.90 rich emerald)
      // Normalize NDVI between 0.35 and 0.90
      const norm = Math.max(0, Math.min(1, (z.ndvi - 0.4) / 0.5));
      if (norm > 0.7) {
        return { backgroundColor: '#065F46', border: '1px solid rgba(255, 255, 255, 0.2)' }; // Deep emerald
      } else if (norm > 0.45) {
        return { backgroundColor: '#059669', border: '1px solid rgba(255, 255, 255, 0.2)' }; // Medium green
      } else if (norm > 0.25) {
        return { backgroundColor: '#10B981', border: '1px solid rgba(255, 255, 255, 0.2)' }; // Light green
      } else {
        return { backgroundColor: '#D97706', border: '1px solid rgba(255, 255, 255, 0.2)' }; // Amber low vigor
      }
    } else {
      // Yield colormap (bu/ac)
      if (z.predictedYield >= 185) {
        return { backgroundColor: '#047857', border: '1px solid rgba(255, 255, 255, 0.2)' }; // Dark green
      } else if (z.predictedYield >= 170) {
        return { backgroundColor: '#10B981', border: '1px solid rgba(255, 255, 255, 0.2)' }; // Emerald
      } else if (z.predictedYield >= 155) {
        return { backgroundColor: '#F59E0B', border: '1px solid rgba(255, 255, 255, 0.2)' }; // Amber
      } else {
        return { backgroundColor: '#DC2626', border: '1px solid rgba(255, 255, 255, 0.2)' }; // Red
      }
    }
  };

  return (
    <div className="bg-white border border-slate-200/90 rounded-lg p-5 shadow-xs transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-100 gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">
              Spatial Field View
            </h3>
            <span className="text-[11px] font-mono text-slate-500">
              {fieldName} · 10m Ground Resolution
            </span>
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Zone-level variability & satellite context. Hover any cell to inspect soil & moisture telemetry.
          </p>
        </div>

        {/* Layer Mode Tabs: [ Satellite ] [ Vegetation ] [ Yield ] */}
        <div className="flex items-center gap-1 p-0.5 bg-slate-100/90 rounded border border-slate-200/60 self-start sm:self-auto">
          <button
            onClick={() => setActiveLayer('satellite')}
            className={`px-3 py-1 text-xs font-medium rounded transition-all cursor-pointer ${
              activeLayer === 'satellite'
                ? 'bg-white text-emerald-950 font-bold shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Satellite
          </button>
          <button
            onClick={() => setActiveLayer('vegetation')}
            className={`px-3 py-1 text-xs font-medium rounded transition-all cursor-pointer ${
              activeLayer === 'vegetation'
                ? 'bg-white text-emerald-950 font-bold shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Vegetation
          </button>
          <button
            onClick={() => setActiveLayer('yield')}
            className={`px-3 py-1 text-xs font-medium rounded transition-all cursor-pointer ${
              activeLayer === 'yield'
                ? 'bg-white text-emerald-950 font-bold shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Yield
          </button>
        </div>
      </div>

      {/* Main Visual Stage & HUD Inspector */}
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-5 items-start">
        {/* Left 2 Cols: Interactive Field Grid Canvas Container */}
        <div className="lg:col-span-2 relative bg-slate-950 rounded-lg p-4 overflow-hidden border border-slate-900 shadow-inner">
          {/* Subtle Map Coordinates Overlay */}
          <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 mb-2.5">
            <div className="flex items-center gap-1.5">
              <Crosshair className="w-3 h-3 text-emerald-400" />
              <span>40°25'25.3"N 86°55'16.3"W</span>
            </div>
            <span>Platform: Sentinel-2 MSI L2A</span>
          </div>

          {/* 4x4 Polygonal Field Zones Matrix */}
          <div className="aspect-16/10 sm:aspect-16/9 w-full grid grid-cols-4 grid-rows-4 gap-1 p-2 bg-slate-900/80 rounded border border-slate-800">
            {zones.map((zone) => {
              const isSelected = hoveredZone?.id === zone.id;
              const style = getZoneStyle(zone);

              return (
                <div
                  key={zone.id}
                  style={style}
                  onMouseEnter={() => setHoveredZone(zone)}
                  onClick={() => setHoveredZone(zone)}
                  className={`relative cursor-pointer transition-all duration-150 flex flex-col justify-between p-1.5 rounded-xs select-none ${
                    isSelected
                      ? 'ring-2 ring-white ring-offset-1 ring-offset-slate-900 z-10 scale-[1.03] shadow-md'
                      : 'hover:brightness-110'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono font-medium text-white/90 drop-shadow-xs">
                      {zone.name.replace('Zone ', 'Z')}
                    </span>
                    {isSelected && (
                      <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping"></span>
                    )}
                  </div>

                  <div className="text-right">
                    <span className="text-[10px] font-mono font-bold text-white drop-shadow-xs">
                      {activeLayer === 'yield'
                        ? `${zone.predictedYield}`
                        : activeLayer === 'vegetation'
                        ? `${zone.ndvi.toFixed(2)}`
                        : `${zone.satelliteReflectance.toFixed(2)}`}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Bottom Colormap Legend */}
          <div className="mt-3 flex items-center justify-between text-[10px] font-mono text-slate-400">
            <div className="flex items-center gap-2">
              <span>Low Vigor</span>
              <div className="w-24 h-2 rounded-full bg-gradient-to-r from-amber-600 via-emerald-500 to-emerald-800 border border-slate-700"></div>
              <span>High Canopy Density</span>
            </div>
            <span className="text-slate-500">16 Sampled Pedon Sectors</span>
          </div>
        </div>

        {/* Right 1 Col: Spatial Zone Inspector HUD (Item 18 of Developer Brief) */}
        <div className="bg-[#FBFBFA] border border-slate-200/90 rounded-lg p-4 h-full flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-200/80">
              <div className="flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-emerald-700" />
                <span className="text-xs font-bold text-slate-900 font-mono">
                  {hoveredZone ? hoveredZone.name : 'Zone 14 (Selected)'}
                </span>
              </div>
              <span className="text-[10px] font-mono text-slate-500 bg-white border border-slate-200 px-1.5 py-0.5 rounded">
                Inspector HUD
              </span>
            </div>

            {hoveredZone ? (
              <div className="space-y-3 font-mono">
                {/* Predicted Yield */}
                <div className="p-2.5 bg-white rounded border border-slate-200/80">
                  <span className="text-[10px] text-slate-500 block uppercase">
                    Predicted Yield
                  </span>
                  <div className="flex items-baseline gap-1 mt-0.5">
                    <span className="text-2xl font-bold text-slate-900">
                      {hoveredZone.predictedYield}
                    </span>
                    <span className="text-xs text-slate-500">bu/ac</span>
                  </div>
                </div>

                {/* NDVI & 30-day rain */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2 bg-white rounded border border-slate-200/80">
                    <span className="text-[10px] text-slate-500 block uppercase">NDVI</span>
                    <span className="text-base font-bold text-emerald-800">
                      {hoveredZone.ndvi.toFixed(2)}
                    </span>
                  </div>
                  <div className="p-2 bg-white rounded border border-slate-200/80">
                    <span className="text-[10px] text-slate-500 block uppercase">30-day rain</span>
                    <span className="text-base font-bold text-blue-700">
                      {hoveredZone.rainfall30Day} mm
                    </span>
                  </div>
                </div>

                {/* Soil Classification */}
                <div className="p-2 bg-white rounded border border-slate-200/80">
                  <span className="text-[10px] text-slate-500 block uppercase">Soil</span>
                  <span className="text-xs font-semibold text-slate-800">
                    {hoveredZone.soil}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-xs text-slate-500 py-8 text-center">
                Hover or click any cell in the field grid to view zone telemetry.
              </div>
            )}
          </div>

          <div className="mt-4 pt-3 border-t border-slate-200/70 text-[10px] text-slate-600 font-mono flex items-center justify-between">
            <span>Tile: 2026-07-21</span>
            <span className="text-emerald-800 font-medium">Ready for GeoTIFF API</span>
          </div>
        </div>
      </div>
    </div>
  );
};
