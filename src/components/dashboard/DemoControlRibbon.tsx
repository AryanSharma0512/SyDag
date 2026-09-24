import React, { useState } from 'react';
import { FieldMeta } from '../../types/agricultural';
import { Sliders, RotateCcw, Presentation, Keyboard, Eye, AlertCircle, Sparkles, X, ChevronDown, ChevronUp } from 'lucide-react';

interface DemoControlRibbonProps {
  fields: FieldMeta[];
  selectedField: FieldMeta;
  onSelectField: (field: FieldMeta) => void;
  isPresentationMode: boolean;
  onTogglePresentationMode: () => void;
  onResetDemo: () => void;
  simulateLoading: boolean;
  onToggleSimulateLoading: () => void;
  simulateMissingSatellite: boolean;
  onToggleSimulateMissingSatellite: () => void;
  simulateWeatherError: boolean;
  onToggleSimulateWeatherError: () => void;
}

export const DemoControlRibbon: React.FC<DemoControlRibbonProps> = ({
  fields,
  selectedField,
  onSelectField,
  isPresentationMode,
  onTogglePresentationMode,
  onResetDemo,
  simulateLoading,
  onToggleSimulateLoading,
  simulateMissingSatellite,
  onToggleSimulateMissingSatellite,
  simulateWeatherError,
  onToggleSimulateWeatherError,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showShortcutsModal, setShowShortcutsModal] = useState(false);

  // In full presentation mode, keep it minimal or hidden unless expanded
  if (isPresentationMode && !isExpanded) {
    return (
      <div className="fixed bottom-4 right-4 z-50">
        <button
          onClick={() => setIsExpanded(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900/90 text-white rounded-md text-xs font-mono shadow-lg hover:bg-slate-800 transition-all border border-slate-700/60"
        >
          <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
          <span>Demo Controls</span>
          <ChevronUp className="w-3 h-3 text-slate-400" />
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="bg-slate-900 text-white border-t border-slate-800 px-4 py-2 transition-all text-xs font-mono z-40 sticky bottom-0">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-2.5">
          {/* Left: Quick Field Switcher (Keys 1-5) */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-slate-400 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block"></span>
              Scenario Switcher:
            </span>
            <div className="flex items-center gap-1">
              {fields.map((f, index) => {
                const isSelected = f.id === selectedField.id;
                return (
                  <button
                    key={f.id}
                    onClick={() => onSelectField(f)}
                    className={`px-2 py-1 rounded text-[11px] font-mono transition-all flex items-center gap-1 cursor-pointer ${
                      isSelected
                        ? 'bg-emerald-500 text-slate-950 font-bold shadow-xs'
                        : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                    }`}
                    title={`Shortcut: ${index + 1}`}
                  >
                    <span className="text-[10px] opacity-60">[{index + 1}]</span>
                    <span>{f.name.replace(' Plot ', ' ')}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right: State Simulators (Loading, Error, Empty) & Mode */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Simulation controls for judges (item 24, 25) */}
            <div className="flex items-center gap-1 border-r border-slate-800 pr-2">
              <button
                onClick={onToggleSimulateLoading}
                className={`px-2 py-1 rounded text-[11px] transition-colors cursor-pointer ${
                  simulateLoading
                    ? 'bg-amber-400 text-slate-950 font-bold'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
                title="Toggle skeleton shimmer loader"
              >
                Simulate Loading
              </button>

              <button
                onClick={onToggleSimulateMissingSatellite}
                className={`px-2 py-1 rounded text-[11px] transition-colors cursor-pointer ${
                  simulateMissingSatellite
                    ? 'bg-amber-400 text-slate-950 font-bold'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
                title="Simulate missing satellite observations (Empty fallback)"
              >
                Missing Satellite
              </button>

              <button
                onClick={onToggleSimulateWeatherError}
                className={`px-2 py-1 rounded text-[11px] transition-colors cursor-pointer ${
                  simulateWeatherError
                    ? 'bg-rose-400 text-slate-950 font-bold'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
                title="Simulate weather endpoint failure (Error fallback)"
              >
                Weather Error
              </button>
            </div>

            {/* Actions: Shortcuts Modal, Reset, Presentation */}
            <button
              onClick={() => setShowShortcutsModal(true)}
              className="p-1 text-slate-400 hover:text-white transition-colors"
              title="View Keyboard Shortcuts"
            >
              <Keyboard className="w-4 h-4" />
            </button>

            <button
              onClick={onResetDemo}
              className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded flex items-center gap-1 cursor-pointer transition-colors"
              title="Reset to default July 22 snapshot (Shortcut: R)"
            >
              <RotateCcw className="w-3 h-3 text-slate-400" />
              <span>Reset [R]</span>
            </button>

            <button
              onClick={onTogglePresentationMode}
              className={`px-2.5 py-1 rounded flex items-center gap-1 transition-colors cursor-pointer ${
                isPresentationMode
                  ? 'bg-emerald-500 text-slate-950 font-bold'
                  : 'bg-slate-800 text-slate-200 hover:bg-slate-700'
              }`}
              title="Toggle Presentation Mode (Shortcut: F or P)"
            >
              <Presentation className="w-3.5 h-3.5" />
              <span>{isPresentationMode ? 'Exit [F]' : 'Present [F]'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Keyboard Shortcuts Modal */}
      {showShortcutsModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-lg shadow-xl border border-slate-200 w-full max-w-md p-5 text-slate-800">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Keyboard className="w-4 h-4 text-emerald-700" />
                <h3 className="text-sm font-bold text-slate-900">
                  Hackathon Presentation Shortcuts
                </h3>
              </div>
              <button
                onClick={() => setShowShortcutsModal(false)}
                className="text-slate-400 hover:text-slate-700"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-4 space-y-2 text-xs font-mono">
              <div className="flex justify-between items-center p-2 rounded bg-[#FBFBFA] border border-slate-100">
                <span className="text-slate-600">Scrub forecast date</span>
                <span className="bg-slate-100 border border-slate-300 px-2 py-0.5 rounded text-slate-900">
                  ← / →
                </span>
              </div>
              <div className="flex justify-between items-center p-2 rounded bg-[#FBFBFA] border border-slate-100">
                <span className="text-slate-600">Quick switch fields (1 to 5)</span>
                <span className="bg-slate-100 border border-slate-300 px-2 py-0.5 rounded text-slate-900">
                  1, 2, 3, 4, 5
                </span>
              </div>
              <div className="flex justify-between items-center p-2 rounded bg-[#FBFBFA] border border-slate-100">
                <span className="text-slate-600">Reset to initial snapshot</span>
                <span className="bg-slate-100 border border-slate-300 px-2 py-0.5 rounded text-slate-900">
                  R
                </span>
              </div>
              <div className="flex justify-between items-center p-2 rounded bg-[#FBFBFA] border border-slate-100">
                <span className="text-slate-600">Toggle presentation mode</span>
                <span className="bg-slate-100 border border-slate-300 px-2 py-0.5 rounded text-slate-900">
                  F or P
                </span>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-100 flex justify-end">
              <button
                onClick={() => setShowShortcutsModal(false)}
                className="px-3 py-1.5 bg-slate-900 text-white rounded text-xs font-medium hover:bg-slate-800 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
