import React from 'react';
import { FieldMeta } from '../../types/agricultural';
import { ChevronDown, MapPin, Calendar, Sprout, Sparkles } from 'lucide-react';

interface FieldContextBarProps {
  fields: FieldMeta[];
  selectedField: FieldMeta;
  onSelectField: (field: FieldMeta) => void;
  activeDateDisplay: string;
  stageName: string;
  isPresentationMode?: boolean;
}

export const FieldContextBar: React.FC<FieldContextBarProps> = ({
  fields,
  selectedField,
  onSelectField,
  activeDateDisplay,
  stageName,
  isPresentationMode = false,
}) => {
  const [dropdownOpen, setDropdownOpen] = React.useState(false);
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="bg-white border-b border-slate-200/90 px-4 sm:px-6 lg:px-8 py-3 transition-all">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Left: Field Selector & Metadata */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          {/* Field Selector */}
          <div className="relative" ref={dropdownRef}>
            <label className="block text-[11px] font-mono uppercase text-slate-600 mb-0.5">
              Field Selection
            </label>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center justify-between gap-2.5 px-3 py-1.5 bg-[#FBFBFA] hover:bg-slate-100 border border-slate-300 rounded text-sm font-semibold text-slate-900 transition-colors focus:outline-none focus:ring-1 focus:ring-emerald-600"
              aria-expanded={dropdownOpen}
            >
              <div className="flex items-center gap-2">
                <MapPin className="w-3.5 h-3.5 text-emerald-700 shrink-0" />
                <span className="whitespace-nowrap">{selectedField.name}</span>
              </div>
              <ChevronDown
                className={`w-3.5 h-3.5 text-slate-500 transition-transform ${
                  dropdownOpen ? 'rotate-180' : ''
                }`}
              />
            </button>

            {/* Dropdown Menu */}
            {dropdownOpen && (
              <div className="absolute left-0 mt-1.5 w-72 bg-white border border-slate-200 rounded-md shadow-lg z-40 py-1 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
                <div className="px-3 py-1.5 text-[11px] font-mono uppercase text-slate-600 border-b border-slate-100">
                  Select Plot for Forecasting
                </div>
                {fields.map((f) => (
                  <button
                    key={f.id}
                    onClick={() => {
                      onSelectField(f);
                      setDropdownOpen(false);
                    }}
                    className={`w-full text-left px-3 py-2 text-xs flex flex-col gap-0.5 hover:bg-slate-50 transition-colors ${
                      f.id === selectedField.id ? 'bg-emerald-50/70 text-emerald-950 font-semibold' : 'text-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-slate-900">{f.name}</span>
                      <span className="text-[10px] font-mono text-slate-600">{f.acreage} ac</span>
                    </div>
                    <span className="text-[11px] text-slate-600 truncate">{f.location}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Crop */}
          <div>
            <span className="block text-[11px] font-mono uppercase text-slate-600 mb-0.5">Crop</span>
            <div className="flex items-center gap-1.5 text-sm font-medium text-slate-800">
              <Sprout className="w-3.5 h-3.5 text-emerald-700 shrink-0" />
              <span>{selectedField.crop}</span>
            </div>
          </div>

          {/* Season */}
          <div>
            <span className="block text-[11px] font-mono uppercase text-slate-600 mb-0.5">Season</span>
            <div className="text-sm font-medium text-slate-800 font-mono">
              {selectedField.season}
            </div>
          </div>

          {/* Forecast Date */}
          <div>
            <span className="block text-[11px] font-mono uppercase text-slate-600 mb-0.5">
              Forecast as of
            </span>
            <div className="flex items-center gap-1.5 text-sm font-semibold text-emerald-900">
              <Calendar className="w-3.5 h-3.5 text-emerald-700 shrink-0" />
              <span>{activeDateDisplay}, {selectedField.season}</span>
            </div>
          </div>
        </div>

        {/* Right: Location & Soil summary */}
        {!isPresentationMode && (
          <div className="hidden lg:flex items-center gap-4 text-xs text-slate-600 border-l border-slate-200/80 pl-5">
            <div>
              <span className="text-slate-600">Growth Stage: </span>
              <span className="font-semibold text-slate-800">{stageName}</span>
            </div>
            <span className="text-slate-300">|</span>
            <div>
              <span className="text-slate-600">Soil: </span>
              <span className="font-medium text-slate-800">{selectedField.soilClassification}</span>
            </div>
            <span className="text-slate-300">|</span>
            <div>
              <span className="text-slate-600">Reg. Baseline: </span>
              <span className="font-mono font-medium text-slate-800">{selectedField.regionalBaseline} bu/ac</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
