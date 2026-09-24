import React from 'react';
import { AlertCircle, RefreshCw, Layers } from 'lucide-react';

export const ModuleSkeleton: React.FC<{ className?: string; height?: string }> = ({
  className = '',
  height = 'h-48',
}) => {
  return (
    <div
      className={`bg-white rounded-lg border border-slate-200/80 p-5 animate-pulse flex flex-col justify-between ${height} ${className}`}
    >
      <div className="space-y-3">
        <div className="h-4 bg-slate-200/70 rounded w-1/4"></div>
        <div className="h-3 bg-slate-100 rounded w-3/4"></div>
      </div>
      <div className="space-y-2">
        <div className="h-8 bg-slate-100 rounded w-1/2"></div>
        <div className="h-3 bg-slate-100 rounded w-full"></div>
      </div>
    </div>
  );
};

export const ErrorCard: React.FC<{
  title: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}> = ({ title, message, onRetry, className = '' }) => {
  return (
    <div
      className={`bg-white rounded-lg border border-amber-200/80 p-5 flex flex-col items-start gap-3 shadow-xs ${className}`}
    >
      <div className="flex items-center gap-2.5 text-amber-800 font-medium text-sm">
        <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
        <span>{title}</span>
      </div>
      <p className="text-xs text-slate-600 leading-relaxed">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 px-3 py-1.5 text-xs font-medium text-slate-700 hover:text-slate-900 border border-slate-300 rounded hover:bg-slate-50 transition-colors flex items-center gap-1.5 cursor-pointer"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Retry</span>
        </button>
      )}
    </div>
  );
};

export const EmptyModuleState: React.FC<{
  title: string;
  subtext: string;
  className?: string;
}> = ({ title, subtext, className = '' }) => {
  return (
    <div
      className={`bg-white rounded-lg border border-dashed border-slate-200 p-8 flex flex-col items-center justify-center text-center text-slate-500 ${className}`}
    >
      <Layers className="w-8 h-8 text-slate-300 mb-2" />
      <h4 className="text-sm font-medium text-slate-700 mb-1">{title}</h4>
      <p className="text-xs text-slate-500 max-w-sm">{subtext}</p>
    </div>
  );
};
