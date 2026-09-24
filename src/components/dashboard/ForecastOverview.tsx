import React from 'react';
import { ForecastSnapshot, FieldMeta } from '../../types/agricultural';
import { useSmoothNumber } from '../../utils/useSmoothNumber';
import { TrendingUp, TrendingDown, Minus, ShieldCheck, Gauge } from 'lucide-react';

interface ForecastOverviewProps {
  snapshot: ForecastSnapshot;
  field: FieldMeta;
  isPresentationMode?: boolean;
}

export const ForecastOverview: React.FC<ForecastOverviewProps> = ({
  snapshot,
  field,
  isPresentationMode = false,
}) => {
  // Smoothly interpolated values for slider transitions (250 - 450 ms)
  const smoothYield = useSmoothNumber(snapshot.yield, 320, 1);
  const smoothLower = useSmoothNumber(snapshot.lowerBound, 320, 1);
  const smoothUpper = useSmoothNumber(snapshot.upperBound, 320, 1);
  const smoothConfidence = useSmoothNumber(snapshot.confidence, 320, 0);

  // Compute delta vs regional 5-year baseline
  const baseline = field.regionalBaseline;
  const deltaPct = ((snapshot.yield - baseline) / baseline) * 100;
  const isPositiveDelta = deltaPct >= 0;

  // Confidence styling
  const confidenceColor =
    snapshot.confidenceRating === 'HIGH'
      ? 'text-emerald-800'
      : snapshot.confidenceRating === 'MODERATE'
      ? 'text-amber-800'
      : 'text-slate-700';

  const confidenceBarBg =
    snapshot.confidenceRating === 'HIGH'
      ? 'bg-emerald-600'
      : snapshot.confidenceRating === 'MODERATE'
      ? 'bg-amber-500'
      : 'bg-slate-400';

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Card 1: Predicted Yield */}
      <div className="bg-white border border-slate-200/90 rounded-lg p-5 shadow-xs transition-all hover:border-slate-300">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-mono uppercase tracking-wider text-slate-600">
            Predicted Yield
          </span>
          <span className="text-[11px] font-mono text-slate-500">
            Updated {snapshot.weather.updatedAgo}
          </span>
        </div>

        <div className="flex items-baseline gap-2">
          <span
            className={`font-mono font-bold tracking-tight text-slate-900 tabular-nums ${
              isPresentationMode ? 'text-5xl' : 'text-4xl'
            }`}
          >
            {smoothYield.toFixed(1)}
          </span>
          <span className="text-sm font-mono text-slate-600 font-medium">bu/ac</span>
        </div>

        <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5">
            {Math.abs(deltaPct) < 0.2 ? (
              <Minus className="w-3.5 h-3.5 text-slate-600" />
            ) : isPositiveDelta ? (
              <TrendingUp className="w-3.5 h-3.5 text-emerald-800" />
            ) : (
              <TrendingDown className="w-3.5 h-3.5 text-rose-800" />
            )}
            <span
              className={`font-medium font-mono ${
                Math.abs(deltaPct) < 0.2
                  ? 'text-slate-600'
                  : isPositiveDelta
                  ? 'text-emerald-800'
                  : 'text-rose-800'
              }`}
            >
              {isPositiveDelta ? '+' : ''}
              {deltaPct.toFixed(1)}%
            </span>
            <span className="text-slate-600">vs regional 5-year baseline</span>
          </div>
          <span className="text-[11px] font-mono text-slate-600">({baseline} bu/ac)</span>
        </div>
      </div>

      {/* Card 2: Forecast Range / Prediction Interval */}
      <div className="bg-white border border-slate-200/90 rounded-lg p-5 shadow-xs transition-all hover:border-slate-300">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-mono uppercase tracking-wider text-slate-600">
            Forecast Range
          </span>
          <span className="text-[11px] font-mono text-slate-600">
            ±{((smoothUpper - smoothLower) / 2).toFixed(1)} spread
          </span>
        </div>

        <div className="flex items-baseline gap-2">
          <span
            className={`font-mono font-semibold tracking-tight text-slate-900 tabular-nums ${
              isPresentationMode ? 'text-3xl' : 'text-2xl'
            }`}
          >
            {smoothLower.toFixed(1)} – {smoothUpper.toFixed(1)}
          </span>
          <span className="text-sm font-mono text-slate-600 font-medium">bu/ac</span>
        </div>

        <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
          <span className="text-slate-600 font-medium">90% prediction interval</span>
          <span className="text-[11px] text-slate-600">
            {snapshot.stage === 'Maturity' ? 'Fixed harvest window' : 'Narrows with later observations'}
          </span>
        </div>
      </div>

      {/* Card 3: Model Confidence */}
      <div className="bg-white border border-slate-200/90 rounded-lg p-5 shadow-xs transition-all hover:border-slate-300">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-mono uppercase tracking-wider text-slate-600">
            Confidence
          </span>
          <div className="flex items-center gap-1 text-slate-600 text-xs">
            <ShieldCheck className="w-3.5 h-3.5 text-slate-500" />
            <span className="font-mono text-[11px]">Ensemble Likelihood</span>
          </div>
        </div>

        <div className="flex items-baseline justify-between">
          <div className="flex items-baseline gap-2">
            <span
              className={`font-mono font-bold tracking-tight ${confidenceColor} tabular-nums ${
                isPresentationMode ? 'text-4xl' : 'text-3xl'
              }`}
            >
              {Math.round(smoothConfidence)}%
            </span>
            <span className={`text-xs font-semibold uppercase tracking-wider ${confidenceColor}`}>
              {snapshot.confidenceRating}
            </span>
          </div>
          <span className="text-[11px] text-slate-600 font-mono">
            {snapshot.confidenceRating === 'HIGH'
              ? 'Multi-sensor consensus'
              : snapshot.confidenceRating === 'MODERATE'
              ? 'Mid-season variance'
              : 'Climatological baseline'}
          </span>
        </div>

        {/* Subtle Horizontal Confidence Indicator (Item 9: Do not use circular gauge) */}
        <div className="mt-3 pt-3 border-t border-slate-100 space-y-1.5">
          <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ease-out ${confidenceBarBg}`}
              style={{ width: `${Math.min(100, Math.max(5, smoothConfidence))}%` }}
              role="progressbar"
              aria-valuenow={Math.round(smoothConfidence)}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
          <div className="flex justify-between text-[10px] font-mono text-slate-600">
            <span>Early Climatology (30%)</span>
            <span>Pre-Harvest Consensus (95%)</span>
          </div>
        </div>
      </div>
    </div>
  );
};
