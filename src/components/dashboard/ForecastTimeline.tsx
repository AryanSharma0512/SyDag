import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ReferenceDot,
  CartesianGrid,
} from 'recharts';
import { ForecastSnapshot, GrowthStage } from '../../types/agricultural';
import { Calendar, HelpCircle, ChevronLeft, ChevronRight, Sliders } from 'lucide-react';

interface ForecastTimelineProps {
  snapshots: ForecastSnapshot[];
  activeSnapshotIndex: number;
  onSelectSnapshotIndex: (index: number) => void;
  isPresentationMode?: boolean;
}

const STAGES: Array<{ id: GrowthStage; name: string; range: string }> = [
  { id: 'Emergence', name: 'Emergence', range: 'May - Early Jun' },
  { id: 'Vegetative', name: 'Vegetative', range: 'Mid Jun - Early Jul' },
  { id: 'Reproductive', name: 'Reproductive', range: 'Mid Jul - Mid Aug' },
  { id: 'Maturity', name: 'Maturity', range: 'Late Aug - Sep' },
];

export const ForecastTimeline: React.FC<ForecastTimelineProps> = ({
  snapshots,
  activeSnapshotIndex,
  onSelectSnapshotIndex,
  isPresentationMode = false,
}) => {
  const activeSnapshot = snapshots[activeSnapshotIndex] || snapshots[0];

  // Prepare chart data format
  // Recharts Area can use an array [lowerBound, upperBound] for range band
  const chartData = snapshots.map((s, index) => {
    const isPastOrCurrent = index <= activeSnapshotIndex;
    return {
      id: s.id,
      index,
      displayDate: s.displayDate,
      date: s.date,
      // For all observations, show the progressive forecast curve
      predictedYield: s.yield,
      // Uncertainty bounds
      lowerBound: s.lowerBound,
      upperBound: s.upperBound,
      // Range tuple for the uncertainty band
      uncertaintyBand: [s.lowerBound, s.upperBound],
      // Confidence & stage
      confidence: s.confidence,
      stage: s.stage,
      isCurrentDate: index === activeSnapshotIndex,
      isObservedByDate: isPastOrCurrent,
    };
  });

  // Calculate Y min and max to keep chart well scaled
  const minY = Math.floor(Math.min(...snapshots.map((s) => s.lowerBound)) / 10) * 10 - 10;
  const maxY = Math.ceil(Math.max(...snapshots.map((s) => s.upperBound)) / 10) * 10 + 10;

  // Growth stage progress indicator
  const getStageActiveState = (stageId: GrowthStage): 'past' | 'current' | 'future' => {
    const currentStage = activeSnapshot.stage;
    const stageOrder: GrowthStage[] = ['Emergence', 'Vegetative', 'Reproductive', 'Maturity'];
    const curIdx = stageOrder.indexOf(currentStage);
    const targetIdx = stageOrder.indexOf(stageId);
    if (curIdx === targetIdx) return 'current';
    if (curIdx > targetIdx) return 'past';
    return 'future';
  };

  return (
    <div className="bg-white border border-slate-200/90 rounded-lg p-5 shadow-xs transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-2">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight flex items-center gap-2">
            Yield Forecast Through the Growing Season
          </h2>
          <p className="text-xs text-slate-600 mt-0.5">
            See how the expected final yield changes as additional observations become available.
          </p>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-xs font-mono text-slate-600">
          <div className="flex items-center gap-1.5">
            <span className="w-3.5 h-0.5 bg-emerald-700 inline-block rounded-full"></span>
            <span>Predicted Yield</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3.5 h-2 bg-emerald-100 border border-emerald-300/80 inline-block rounded-xs"></span>
            <span>90% Uncertainty Band</span>
          </div>
        </div>
      </div>

      {/* Main Chart */}
      <div className={`w-full mt-4 ${isPresentationMode ? 'h-72' : 'h-64 sm:h-72'}`}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 15, right: 20, left: 0, bottom: 5 }}
            onClick={(e) => {
              if (e && typeof e.activeTooltipIndex === 'number') {
                onSelectSnapshotIndex(e.activeTooltipIndex);
              }
            }}
          >
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
            <XAxis
              dataKey="displayDate"
              stroke="#64748B"
              fontSize={11}
              fontFamily="JetBrains Mono"
              tickLine={false}
              axisLine={{ stroke: '#CBD5E1' }}
              dy={6}
            />
            <YAxis
              domain={[minY, maxY]}
              stroke="#64748B"
              fontSize={11}
              fontFamily="JetBrains Mono"
              tickLine={false}
              axisLine={{ stroke: '#CBD5E1' }}
              tickFormatter={(v) => `${v}`}
              dx={-4}
            />

            {/* Custom Tooltip */}
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload;
                  return (
                    <div className="bg-slate-900 text-white rounded-md p-2.5 shadow-md border border-slate-800 text-xs font-mono pointer-events-none">
                      <div className="flex items-center justify-between gap-3 text-slate-400 border-b border-slate-800 pb-1 mb-1.5">
                        <span className="font-semibold text-white">{data.displayDate}, 2026</span>
                        <span className="text-[10px] text-emerald-400">{data.stage}</span>
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between gap-4">
                          <span className="text-slate-400">Yield Forecast:</span>
                          <span className="font-bold text-emerald-300">{data.predictedYield} bu/ac</span>
                        </div>
                        <div className="flex justify-between gap-4">
                          <span className="text-slate-400">90% Range:</span>
                          <span className="text-slate-200">
                            {data.lowerBound} – {data.upperBound}
                          </span>
                        </div>
                        <div className="flex justify-between gap-4">
                          <span className="text-slate-400">Confidence:</span>
                          <span className="text-slate-200">{data.confidence}%</span>
                        </div>
                      </div>
                    </div>
                  );
                }
                return null;
              }}
            />

            {/* 90% Prediction Interval Band */}
            <Area
              type="monotone"
              dataKey="uncertaintyBand"
              fill="#D1FAE5"
              fillOpacity={0.65}
              stroke="#10B981"
              strokeWidth={1}
              strokeDasharray="2 2"
              name="90% Prediction Interval"
              isAnimationActive={true}
              animationDuration={350}
            />

            {/* Predicted Yield Line */}
            <Line
              type="monotone"
              dataKey="predictedYield"
              stroke="#047857"
              strokeWidth={2.5}
              dot={{ r: 3.5, fill: '#047857', stroke: '#FFFFFF', strokeWidth: 1.5 }}
              activeDot={{ r: 6, fill: '#065F46', stroke: '#FFFFFF', strokeWidth: 2 }}
              name="Yield Forecast"
              isAnimationActive={true}
              animationDuration={350}
            />

            {/* Vertical Marker for Selected Forecast Date */}
            <ReferenceLine
              x={activeSnapshot.displayDate}
              stroke="#047857"
              strokeWidth={2}
              strokeDasharray="4 4"
              label={{
                value: `Selected: ${activeSnapshot.displayDate}`,
                position: 'top',
                fill: '#065F46',
                fontSize: 10,
                fontFamily: 'JetBrains Mono',
                fontWeight: 600,
                offset: 10,
              }}
            />

            {/* Dot at Current Value */}
            <ReferenceDot
              x={activeSnapshot.displayDate}
              y={activeSnapshot.yield}
              r={6}
              fill="#065F46"
              stroke="#FFFFFF"
              strokeWidth={2}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Date Slider & Scrubbing Controls (Item 11 of Developer Brief) */}
      <div className="mt-5 pt-4 border-t border-slate-100">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Sliders className="w-3.5 h-3.5 text-emerald-700" />
            <span className="text-xs font-semibold text-slate-900 tracking-tight">
              Forecast Date Slider
            </span>
            <span className="text-[11px] text-slate-500 hidden sm:inline">
              — What could the system have predicted using only information available by this date?
            </span>
          </div>

          <div className="flex items-center gap-1.5 text-xs font-mono font-semibold text-emerald-900 bg-emerald-50/90 border border-emerald-200/60 px-2 py-0.5 rounded">
            <Calendar className="w-3 h-3 text-emerald-700" />
            <span>{activeSnapshot.displayDate}, 2026</span>
          </div>
        </div>

        {/* Range Slider Track */}
        <div className="relative px-1 py-1">
          <input
            type="range"
            min={0}
            max={snapshots.length - 1}
            step={1}
            value={activeSnapshotIndex}
            onChange={(e) => onSelectSnapshotIndex(parseInt(e.target.value, 10))}
            className="w-full slider-custom focus:outline-none"
            aria-label="Select forecast date through growing season"
          />

          {/* Stepper Buttons for Quick Navigation */}
          <div className="flex justify-between items-center mt-2 text-[11px] font-mono text-slate-600">
            <button
              onClick={() => onSelectSnapshotIndex(Math.max(0, activeSnapshotIndex - 1))}
              disabled={activeSnapshotIndex === 0}
              className="px-2 py-1 border border-slate-200 rounded hover:bg-slate-50 disabled:opacity-30 disabled:pointer-events-none flex items-center gap-0.5 text-slate-700 transition-colors"
              title="Previous date (Shortcut: ←)"
            >
              <ChevronLeft className="w-3 h-3" />
              <span>Prior</span>
            </button>

            {/* Step Date Ticks */}
            <div className="flex items-center gap-1 sm:gap-2">
              {snapshots.map((s, idx) => (
                <button
                  key={s.id}
                  onClick={() => onSelectSnapshotIndex(idx)}
                  className={`px-1.5 py-0.5 rounded text-[10px] transition-colors ${
                    idx === activeSnapshotIndex
                      ? 'bg-emerald-800 text-white font-semibold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                >
                  {s.displayDate}
                </button>
              ))}
            </div>

            <button
              onClick={() =>
                onSelectSnapshotIndex(Math.min(snapshots.length - 1, activeSnapshotIndex + 1))
              }
              disabled={activeSnapshotIndex === snapshots.length - 1}
              className="px-2 py-1 border border-slate-200 rounded hover:bg-slate-50 disabled:opacity-30 disabled:pointer-events-none flex items-center gap-0.5 text-slate-700 transition-colors"
              title="Next date (Shortcut: →)"
            >
              <span>Later</span>
              <ChevronRight className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Subtle Visual Concept: Data Flowing through the Growing Season (Item 31 of Brief) */}
        <div className="mt-4 pt-3 border-t border-slate-100">
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="text-[11px] font-mono uppercase text-slate-600">
              Crop Phenological Stage
            </span>
            <span className="text-[11px] text-slate-600 font-medium">
              {activeSnapshot.stageSubtext}
            </span>
          </div>

          <div className="grid grid-cols-4 gap-1.5 relative">
            {STAGES.map((stg) => {
              const state = getStageActiveState(stg.id);
              return (
                <div
                  key={stg.id}
                  className={`p-2 rounded border transition-all text-center ${
                    state === 'current'
                      ? 'bg-emerald-50/90 border-emerald-400 ring-1 ring-emerald-500/20 shadow-xs'
                      : state === 'past'
                      ? 'bg-slate-50 border-slate-200/90 text-slate-700'
                      : 'bg-white border-slate-200/50 text-slate-500'
                  }`}
                >
                  <div className="flex items-center justify-center gap-1.5 mb-0.5">
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        state === 'current'
                          ? 'bg-emerald-700 ring-2 ring-emerald-400/30'
                          : state === 'past'
                          ? 'bg-slate-500'
                          : 'bg-slate-300'
                      }`}
                    />
                    <span
                      className={`text-[11px] font-semibold tracking-tight ${
                        state === 'current'
                          ? 'text-emerald-950 font-bold'
                          : state === 'past'
                          ? 'text-slate-800'
                          : 'text-slate-500'
                      }`}
                    >
                      {stg.name}
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-600 block">{stg.range}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
