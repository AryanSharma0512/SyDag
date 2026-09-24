import React, { useState } from 'react';
import { ModelExplanation as IModelExplanation, FeatureImportanceItem } from '../../types/agricultural';
import { ChevronDown, ChevronUp, CheckCircle2, AlertTriangle, HelpCircle, Activity } from 'lucide-react';

interface ModelExplanationProps {
  explanations: IModelExplanation[];
  featureImportance: FeatureImportanceItem[];
}

export const ModelExplanation: React.FC<ModelExplanationProps> = ({
  explanations,
  featureImportance,
}) => {
  const [detailsOpen, setDetailsOpen] = useState(false);

  const getInfluenceBadge = (influence: IModelExplanation['influence']) => {
    switch (influence) {
      case 'positive':
        return {
          icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-800 shrink-0" />,
          label: 'Positive influence',
          classes: 'text-emerald-900 bg-emerald-50/80 border-emerald-200/60',
        };
      case 'negative':
        return {
          icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-800 shrink-0" />,
          label: 'Negative influence',
          classes: 'text-amber-900 bg-amber-50/80 border-amber-200/60',
        };
      case 'neutral':
      default:
        return {
          icon: <HelpCircle className="w-3.5 h-3.5 text-slate-600 shrink-0" />,
          label: 'Neutral / buffering influence',
          classes: 'text-slate-800 bg-slate-100 border-slate-200',
        };
    }
  };

  return (
    <div className="bg-white border border-slate-200/90 rounded-lg p-5 shadow-xs transition-all">
      {/* Section Header */}
      <div className="pb-3 border-b border-slate-100">
        <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
          Why is the model predicting this?
        </h3>
        <p className="text-[11px] text-slate-500 mt-0.5">
          Key agro-environmental signals associated with current projection, synthesized across satellite, weather, and soil horizons.
        </p>
      </div>

      {/* Influence Cards (Item 19: Non-causal wording, domain rigor) */}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3.5">
        {explanations.map((item) => {
          const badge = getInfluenceBadge(item.influence);

          return (
            <div
              key={item.id}
              className="p-3.5 rounded-lg border border-slate-200/80 bg-[#FBFBFA] flex flex-col justify-between hover:border-slate-300 transition-colors"
            >
              <div>
                {/* Influence Status Row */}
                <div className="flex items-center justify-between mb-2">
                  <div
                    className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-medium border ${badge.classes}`}
                  >
                    {badge.icon}
                    <span>{item.influenceLabel}</span>
                  </div>
                </div>

                {/* Title */}
                <h4 className="text-xs font-semibold text-slate-900 mb-1.5 leading-snug">
                  {item.title}
                </h4>

                {/* Body Explanation */}
                <p className="text-xs text-slate-600 leading-relaxed">
                  {item.description}
                </p>
              </div>

              {item.metricReference && (
                <div className="mt-3 pt-2 border-t border-slate-200/60 text-[10px] font-mono text-slate-600">
                  {item.metricReference}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Technical Details Toggle (Item 20 of Brief) */}
      <div className="mt-4 pt-3 border-t border-slate-100">
        <button
          onClick={() => setDetailsOpen(!detailsOpen)}
          className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 hover:text-slate-900 focus:outline-none cursor-pointer"
        >
          <Activity className="w-3.5 h-3.5 text-emerald-800" />
          <span>{detailsOpen ? 'Hide technical details' : 'View technical details'}</span>
          {detailsOpen ? (
            <ChevronUp className="w-3.5 h-3.5 text-slate-500" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
          )}
        </button>

        {/* Collapsed/Expanded Feature Importance Drawer */}
        {detailsOpen && (
          <div className="mt-3 p-4 bg-slate-50 rounded-lg border border-slate-200/80 animate-in fade-in duration-150">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-2 mb-3 border-b border-slate-200 gap-1">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-800">
                Model Signals & Feature Weight Distribution
              </span>
              <span className="text-[11px] text-slate-600">
                Feature contribution values derived from model explainability analysis.
              </span>
            </div>

            {/* Horizontal Feature Importance Bars */}
            <div className="space-y-2.5">
              {featureImportance.map((feat) => {
                const barColor =
                  feat.category === 'Vegetation'
                    ? 'bg-emerald-600'
                    : feat.category === 'Weather'
                    ? 'bg-blue-600'
                    : feat.category === 'Soil'
                    ? 'bg-amber-600'
                    : 'bg-slate-500';

                return (
                  <div key={feat.name} className="flex items-center gap-3 text-xs">
                    {/* Feature Label */}
                    <div className="w-44 sm:w-52 shrink-0 flex items-center justify-between">
                      <span className="font-mono text-slate-800 truncate" title={feat.name}>
                        {feat.name}
                      </span>
                      <span className="text-[10px] text-slate-600 font-mono hidden sm:inline ml-1">
                        [{feat.category}]
                      </span>
                    </div>

                    {/* Bar Track */}
                    <div className="flex-1 bg-slate-200/80 rounded-full h-2.5 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-300 ${barColor}`}
                        style={{ width: `${Math.min(100, Math.max(4, feat.weight * 2.8))}%` }}
                      />
                    </div>

                    {/* Value */}
                    <span className="w-10 text-right font-mono font-semibold text-slate-900 tabular-nums">
                      {feat.weight}%
                    </span>
                  </div>
                );
              })}
            </div>

            <div className="mt-3 pt-2 text-[10px] text-slate-600 font-mono flex items-center justify-between">
              <span>Method: Gradient feature attribution across temporal lag sequence</span>
              <span>Model baseline: 10-year county historical distribution</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
