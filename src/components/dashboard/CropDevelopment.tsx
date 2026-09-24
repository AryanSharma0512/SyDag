import React, { useState } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ReferenceDot,
  CartesianGrid,
} from 'recharts';
import { VegetationObservation, EventMarker } from '../../types/agricultural';
import { Info, CloudRain, Sun, Flame, Sparkles } from 'lucide-react';

interface CropDevelopmentProps {
  timeline: VegetationObservation[];
  events: EventMarker[];
  activeDateDisplay: string;
  activeDateIso: string;
}

export const CropDevelopment: React.FC<CropDevelopmentProps> = ({
  timeline,
  events,
  activeDateDisplay,
  activeDateIso,
}) => {
  // Toggle between single active index: NDVI or NDRE
  const [activeSignal, setActiveSignal] = useState<'ndvi' | 'ndre'>('ndvi');
  const [hoveredEvent, setHoveredEvent] = useState<EventMarker | null>(null);

  // Find index of current forecast date in timeline
  const activeDatePoint =
    timeline.find((t) => t.displayDate === activeDateDisplay) ||
    timeline[Math.floor(timeline.length / 2)];

  // For responsive time-series truncation:
  // Points after the selected forecast date are rendered differently (e.g. not observed yet)
  const activeIsoTime = new Date(activeDateIso).getTime();

  const formattedData = timeline.map((pt) => {
    const ptTime = new Date(pt.date).getTime();
    const isObserved = ptTime <= activeIsoTime;

    return {
      date: pt.date,
      displayDate: pt.displayDate,
      // Only show observed value up to active date; future is null for the primary observed line
      observedVal: isObserved ? (activeSignal === 'ndvi' ? pt.ndvi : pt.ndre) : null,
      fullVal: activeSignal === 'ndvi' ? pt.ndvi : pt.ndre,
      baselineVal: pt.regionalBaselineNdvi,
      isObserved,
      isCurrentMarker: pt.displayDate === activeDateDisplay,
    };
  });

  const getEventIcon = (type: EventMarker['type']) => {
    switch (type) {
      case 'rain':
        return <CloudRain className="w-3.5 h-3.5 text-blue-600" />;
      case 'heat':
        return <Flame className="w-3.5 h-3.5 text-rose-600" />;
      case 'dry':
        return <Sun className="w-3.5 h-3.5 text-amber-600" />;
      case 'recovery':
      default:
        return <Sparkles className="w-3.5 h-3.5 text-emerald-600" />;
    }
  };

  return (
    <div className="bg-white border border-slate-200/90 rounded-lg p-5 shadow-xs transition-all h-full flex flex-col justify-between">
      <div>
        {/* Header & Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-100 gap-2">
          <div>
            <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
              Crop Development
            </h3>
            <p className="text-[11px] text-slate-500">
              Multispectral canopy reflection through vegetative & reproductive cycles.
            </p>
          </div>

          {/* Index Selector Tabs (NDVI vs NDRE) */}
          <div className="flex items-center gap-1 p-0.5 bg-slate-100/90 rounded border border-slate-200/60 self-start sm:self-auto">
            <button
              onClick={() => setActiveSignal('ndvi')}
              className={`px-2.5 py-1 text-xs font-mono font-medium rounded transition-all cursor-pointer ${
                activeSignal === 'ndvi'
                  ? 'bg-white text-emerald-950 font-bold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              NDVI
            </button>
            <button
              onClick={() => setActiveSignal('ndre')}
              className={`px-2.5 py-1 text-xs font-mono font-medium rounded transition-all cursor-pointer ${
                activeSignal === 'ndre'
                  ? 'bg-white text-emerald-950 font-bold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              NDRE
            </button>
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center justify-between mt-3 text-[11px] font-mono text-slate-500">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-emerald-600 inline-block"></span>
              <span className="text-slate-700">Observed {activeSignal.toUpperCase()}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-slate-400 border-b border-dashed border-slate-400 inline-block"></span>
              <span className="text-slate-500">5-Yr Baseline</span>
            </div>
          </div>
          <span className="text-[10px] text-slate-400">Vertical line = Selected Date</span>
        </div>

        {/* Chart */}
        <div className="h-48 sm:h-52 w-full mt-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={formattedData}
              margin={{ top: 10, right: 15, left: -15, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
              <XAxis
                dataKey="displayDate"
                stroke="#64748B"
                fontSize={10}
                fontFamily="JetBrains Mono"
                tickLine={false}
                axisLine={{ stroke: '#E2E8F0' }}
              />
              <YAxis
                domain={[0, 1.0]}
                stroke="#64748B"
                fontSize={10}
                fontFamily="JetBrains Mono"
                tickLine={false}
                axisLine={{ stroke: '#E2E8F0' }}
                tickFormatter={(v) => v.toFixed(1)}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const data = payload[0].payload;
                    return (
                      <div className="bg-slate-900 text-white rounded p-2 text-xs font-mono border border-slate-800 pointer-events-none shadow-md">
                        <div className="text-slate-400 font-semibold mb-1">
                          {data.displayDate}
                        </div>
                        <div className="space-y-0.5">
                          <div className="flex justify-between gap-4">
                            <span className="text-emerald-400 font-bold uppercase">
                              {activeSignal}:
                            </span>
                            <span>{data.fullVal.toFixed(2)}</span>
                          </div>
                          <div className="flex justify-between gap-4 text-slate-400">
                            <span>Baseline:</span>
                            <span>{data.baselineVal.toFixed(2)}</span>
                          </div>
                          <div className="text-[10px] pt-1 border-t border-slate-800 text-slate-400">
                            {data.isObserved ? 'Observed by selected date' : 'Future trajectory'}
                          </div>
                        </div>
                      </div>
                    );
                  }
                  return null;
                }}
              />

              {/* Baseline reference line (Dashed) */}
              <Line
                type="monotone"
                dataKey="baselineVal"
                stroke="#94A3B8"
                strokeWidth={1.5}
                strokeDasharray="3 3"
                dot={false}
                isAnimationActive={false}
              />

              {/* Observed line (Solid Green) */}
              <Line
                type="monotone"
                dataKey="observedVal"
                stroke="#059669"
                strokeWidth={2.2}
                dot={{ r: 3, fill: '#059669', stroke: '#FFFFFF', strokeWidth: 1.5 }}
                isAnimationActive={true}
                animationDuration={300}
              />

              {/* Vertical Reference for Active Date */}
              <ReferenceLine
                x={activeDateDisplay}
                stroke="#047857"
                strokeWidth={1.5}
                strokeDasharray="3 3"
              />

              {/* Active Marker Dot */}
              {activeDatePoint && (
                <ReferenceDot
                  x={activeDatePoint.displayDate}
                  y={activeSignal === 'ndvi' ? activeDatePoint.ndvi : activeDatePoint.ndre}
                  r={5}
                  fill="#065F46"
                  stroke="#FFFFFF"
                  strokeWidth={2}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Event Markers Section (Item 14 of Brief) */}
      <div className="mt-3 pt-3 border-t border-slate-100">
        <div className="flex items-center justify-between text-xs mb-2">
          <span className="text-[11px] font-mono uppercase text-slate-600">
            Timeline Field Events
          </span>
          <span className="text-[10px] text-slate-500">Hover marker for details</span>
        </div>

        {/* Small contextual event chips */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
          {events.map((evt) => (
            <div
              key={evt.date}
              onMouseEnter={() => setHoveredEvent(evt)}
              onMouseLeave={() => setHoveredEvent(null)}
              className="p-1.5 rounded border border-slate-200 hover:border-slate-300 hover:bg-slate-50 cursor-pointer transition-colors text-left group relative"
            >
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-[10px] font-mono text-slate-600">{evt.displayDate}</span>
                {getEventIcon(evt.type)}
              </div>
              <p className="text-[11px] font-medium text-slate-800 truncate group-hover:text-emerald-950">
                {evt.title}
              </p>
              <span className="text-[10px] text-slate-600 block truncate">{evt.summary}</span>

              {/* Tooltip on hover */}
              {hoveredEvent?.date === evt.date && (
                <div className="absolute bottom-full left-0 mb-1 z-30 w-52 p-2 bg-slate-900 text-white text-[11px] rounded shadow-lg border border-slate-800 leading-tight">
                  <div className="font-semibold text-emerald-300 mb-0.5">
                    {evt.displayDate} — {evt.title}
                  </div>
                  <p className="text-slate-300 text-[10px]">{evt.hoverDetail}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
