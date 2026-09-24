import React from 'react';
import { HistoricalContext } from '../../types/agricultural';
import { BarChart3, TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface HistoricalComparisonProps {
  historical: HistoricalContext;
  currentForecastYield: number;
}

export const HistoricalComparison: React.FC<HistoricalComparisonProps> = ({
  historical,
  currentForecastYield,
}) => {
  const baseline = historical.regional5YearAvg;
  const deltaPct = ((currentForecastYield - baseline) / baseline) * 100;
  const isPositive = deltaPct >= 0;

  // Max yield for scaling the horizontal bars
  const maxY = Math.max(...historical.yearlyYields.map((y) => y.yield), currentForecastYield) * 1.1;

  return (
    <div className="bg-white border border-slate-200/90 rounded-lg p-5 shadow-xs transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-100 gap-2">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
            Historical Context
          </h3>
          <p className="text-[11px] text-slate-500">
            Multi-year regional performance benchmark (USDA NASS county distribution).
          </p>
        </div>

        {/* Metric summary badges */}
        <div className="flex items-center gap-3 text-xs font-mono">
          <div className="px-2.5 py-1 bg-[#FBFBFA] border border-slate-200 rounded">
            <span className="text-slate-500 mr-1.5">5-Yr Avg:</span>
            <span className="font-bold text-slate-800">{baseline.toFixed(1)} bu/ac</span>
          </div>

          <div
            className={`px-2.5 py-1 rounded border flex items-center gap-1 font-semibold ${
              Math.abs(deltaPct) < 0.2
                ? 'bg-slate-50 border-slate-200 text-slate-700'
                : isPositive
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : 'bg-rose-50 border-rose-200 text-rose-800'
            }`}
          >
            {Math.abs(deltaPct) < 0.2 ? (
              <Minus className="w-3 h-3 text-slate-600" />
            ) : isPositive ? (
              <TrendingUp className="w-3 h-3 text-emerald-700" />
            ) : (
              <TrendingDown className="w-3 h-3 text-rose-700" />
            )}
            <span>
              {isPositive ? '+' : ''}
              {deltaPct.toFixed(1)}% vs Avg
            </span>
          </div>
        </div>
      </div>

      {/* Mini Horizontal Bar Comparison Chart */}
      <div className="mt-4 space-y-2">
        {historical.yearlyYields.map((item) => {
          const isForecast = item.type === 'forecast';
          const yieldVal = isForecast ? currentForecastYield : item.yield;
          const barWidthPercent = (yieldVal / maxY) * 100;

          return (
            <div key={item.year} className="flex items-center gap-3 text-xs">
              {/* Year label */}
              <div className="w-20 shrink-0 font-mono text-slate-700 flex items-center justify-between">
                <span className={isForecast ? 'font-bold text-emerald-900' : 'text-slate-600'}>
                  {isForecast ? '2026 Forecast' : item.year}
                </span>
              </div>

              {/* Bar */}
              <div className="flex-1 bg-slate-100 rounded h-3 overflow-hidden">
                <div
                  className={`h-full rounded transition-all duration-300 ${
                    isForecast
                      ? 'bg-emerald-700'
                      : item.yield >= baseline
                      ? 'bg-slate-400'
                      : 'bg-slate-300'
                  }`}
                  style={{ width: `${barWidthPercent}%` }}
                />
              </div>

              {/* Number */}
              <div className="w-16 text-right font-mono font-medium text-slate-800 tabular-nums">
                {yieldVal.toFixed(1)} <span className="text-[10px] text-slate-500 font-normal">bu</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Subtle baseline line explanation */}
      <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-600 font-mono">
        <span>Dataset: USDA NASS Quick Stats (Tippecanoe County Maize Yields)</span>
        <span>Regional Baseline: {baseline.toFixed(1)} bu/ac</span>
      </div>
    </div>
  );
};
