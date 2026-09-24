import React from 'react';
import { DataSource } from '../../types/agricultural';
import { Database, Clock, Radio, CheckCircle, ShieldCheck } from 'lucide-react';

interface DataSourcesProps {
  sources: DataSource[];
  forecastGeneratedAt: string;
}

export const DataSources: React.FC<DataSourcesProps> = ({
  sources,
  forecastGeneratedAt,
}) => {
  return (
    <div className="bg-white border border-slate-200/90 rounded-lg p-5 shadow-xs transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-100 gap-2">
        <div>
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-700" />
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">
              Data Behind This Forecast
            </h3>
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Transparent data provenance, temporal cadence, and ground-truth validation pipelines.
          </p>
        </div>

        <div className="flex items-center gap-1.5 text-xs font-mono text-slate-600 bg-slate-50 border border-slate-200 px-2.5 py-1 rounded">
          <Clock className="w-3.5 h-3.5 text-slate-500" />
          <span>Inference: {forecastGeneratedAt}</span>
        </div>
      </div>

      {/* Grid of Compact Source Cards */}
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
        {sources.map((src) => (
          <div
            key={src.id}
            className="p-3 rounded-md border border-slate-200/80 bg-[#FBFBFA] flex flex-col justify-between hover:border-slate-300 transition-colors"
          >
            <div>
              {/* Badge & Status */}
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-mono font-medium text-emerald-800 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200/60">
                  {src.badge}
                </span>
                <span className="flex items-center gap-1 text-[10px] font-mono text-emerald-700">
                  <CheckCircle className="w-3 h-3" />
                  <span>Verified</span>
                </span>
              </div>

              {/* Title */}
              <h4 className="text-xs font-bold text-slate-900 leading-tight">
                {src.name}
              </h4>

              {/* Source agency */}
              <p className="text-[11px] text-slate-600 mt-1 leading-snug">
                {src.source}
              </p>
            </div>

            {/* Resolution and freshness footer */}
            <div className="mt-3 pt-2 border-t border-slate-200/60 space-y-1 text-[10px] font-mono text-slate-600">
              <div className="flex justify-between">
                <span className="text-slate-600">Res:</span>
                <span className="text-slate-800 font-medium truncate ml-1">{src.resolution}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-600">Sync:</span>
                <span className="text-slate-800 font-medium truncate ml-1">{src.lastObservation}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
