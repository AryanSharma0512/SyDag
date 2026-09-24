import React from 'react';
import { APP_CONFIG } from '../../config/appConfig';
import { RotateCcw, Presentation, Database, Menu, X } from 'lucide-react';

interface NavigationProps {
  currentRoute: 'landing' | 'dashboard' | 'about';
  onRouteChange: (route: 'landing' | 'dashboard' | 'about') => void;
  isPresentationMode?: boolean;
  onTogglePresentationMode?: () => void;
  onResetDemo?: () => void;
}

export const Navigation: React.FC<NavigationProps> = ({
  currentRoute,
  onRouteChange,
  isPresentationMode = false,
  onTogglePresentationMode,
  onResetDemo,
}) => {
  const [mobileMenuOpen, setMobileMenuOpen] = React.useState(false);

  // If in presentation mode, render a minimized, unobtrusive top bar
  if (isPresentationMode) {
    return (
      <header className="sticky top-0 z-50 bg-[#FBFBFA]/95 backdrop-blur-md border-b border-slate-200/80 px-4 py-2 transition-all">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-base font-semibold tracking-tight text-slate-900">
              {APP_CONFIG.name}
            </span>
            <span className="text-xs text-emerald-800 font-mono bg-emerald-50/90 border border-emerald-200/60 px-2 py-0.5 rounded">
              Presentation Mode
            </span>
          </div>

          <div className="flex items-center gap-2">
            {onResetDemo && (
              <button
                onClick={onResetDemo}
                title="Reset demo (Shortcut: R)"
                className="px-2.5 py-1 text-xs font-medium text-slate-600 hover:text-slate-900 border border-slate-200 hover:border-slate-300 rounded bg-white transition-colors flex items-center gap-1.5"
              >
                <RotateCcw className="w-3.5 h-3.5 text-slate-500" />
                <span className="hidden sm:inline">Reset</span>
              </button>
            )}
            {onTogglePresentationMode && (
              <button
                onClick={onTogglePresentationMode}
                title="Exit presentation mode (Shortcut: F)"
                className="px-2.5 py-1 text-xs font-medium text-slate-700 hover:text-slate-900 border border-slate-300 rounded bg-white transition-colors flex items-center gap-1.5"
              >
                <Presentation className="w-3.5 h-3.5 text-emerald-700" />
                <span>Exit (F)</span>
              </button>
            )}
          </div>
        </div>
      </header>
    );
  }

  return (
    <header className="sticky top-0 z-50 bg-[#FBFBFA]/90 backdrop-blur-md border-b border-slate-200/80 px-4 sm:px-6 lg:px-8 py-3.5 transition-all">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        {/* Zone 1: Single text element wordmark */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => onRouteChange('landing')}
            className="text-left group cursor-pointer focus:outline-none"
          >
            <span className="text-xl font-bold tracking-tight text-slate-900 group-hover:text-emerald-800 transition-colors">
              {APP_CONFIG.name}
            </span>
          </button>
        </div>

        {/* Zone 2: Clean text navigation links */}
        <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-600">
          <button
            onClick={() => onRouteChange('dashboard')}
            className={`transition-colors hover:text-slate-900 relative py-1 focus:outline-none ${
              currentRoute === 'dashboard'
                ? 'text-emerald-800 font-semibold'
                : 'text-slate-600'
            }`}
          >
            Dashboard
            {currentRoute === 'dashboard' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-700 rounded-full" />
            )}
          </button>

          <button
            onClick={() => onRouteChange('about')}
            className={`transition-colors hover:text-slate-900 relative py-1 focus:outline-none ${
              currentRoute === 'about'
                ? 'text-emerald-800 font-semibold'
                : 'text-slate-600'
            }`}
          >
            Methodology & Data Sources
            {currentRoute === 'about' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-700 rounded-full" />
            )}
          </button>

          <button
            onClick={() => onRouteChange('landing')}
            className={`transition-colors hover:text-slate-900 relative py-1 focus:outline-none ${
              currentRoute === 'landing'
                ? 'text-emerald-800 font-semibold'
                : 'text-slate-600'
            }`}
          >
            Overview
            {currentRoute === 'landing' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-700 rounded-full" />
            )}
          </button>
        </nav>

        {/* Zone 3: Dataset badge + Quick presentation button */}
        <div className="hidden sm:flex items-center gap-2.5">
          <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono text-slate-600 bg-slate-100 border border-slate-200/70 rounded">
            <Database className="w-3.5 h-3.5 text-emerald-700" />
            <span className="whitespace-nowrap">{APP_CONFIG.datasetLabel}</span>
          </div>

          {onTogglePresentationMode && (
            <button
              onClick={onTogglePresentationMode}
              title="Presentation Mode (Shortcut: F)"
              className="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded transition-colors focus:outline-none"
              aria-label="Toggle presentation mode"
            >
              <Presentation className="w-4 h-4" />
            </button>
          )}

          {onResetDemo && (
            <button
              onClick={onResetDemo}
              title="Reset Demo to Defaults (Shortcut: R)"
              className="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded transition-colors focus:outline-none"
              aria-label="Reset demo"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Mobile menu toggle */}
        <div className="flex sm:hidden items-center gap-2">
          <div className="text-[11px] font-mono text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
            Demo
          </div>
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-1.5 text-slate-600 hover:text-slate-900 focus:outline-none"
            aria-label="Toggle menu"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile nav drawer */}
      {mobileMenuOpen && (
        <div className="sm:hidden pt-3 pb-2 border-t border-slate-200 mt-3 flex flex-col gap-2">
          <button
            onClick={() => {
              onRouteChange('dashboard');
              setMobileMenuOpen(false);
            }}
            className={`text-left px-3 py-2 rounded text-sm font-medium ${
              currentRoute === 'dashboard'
                ? 'bg-emerald-50 text-emerald-800'
                : 'text-slate-700 hover:bg-slate-50'
            }`}
          >
            Dashboard
          </button>
          <button
            onClick={() => {
              onRouteChange('about');
              setMobileMenuOpen(false);
            }}
            className={`text-left px-3 py-2 rounded text-sm font-medium ${
              currentRoute === 'about'
                ? 'bg-emerald-50 text-emerald-800'
                : 'text-slate-700 hover:bg-slate-50'
            }`}
          >
            Methodology & Data Sources
          </button>
          <button
            onClick={() => {
              onRouteChange('landing');
              setMobileMenuOpen(false);
            }}
            className={`text-left px-3 py-2 rounded text-sm font-medium ${
              currentRoute === 'landing'
                ? 'bg-emerald-50 text-emerald-800'
                : 'text-slate-700 hover:bg-slate-50'
            }`}
          >
            Project Overview
          </button>
          <div className="pt-2 flex items-center justify-between px-3 text-xs text-slate-500 border-t border-slate-100">
            <span>Dataset: {APP_CONFIG.datasetLabel}</span>
            {onResetDemo && (
              <button
                onClick={() => {
                  onResetDemo();
                  setMobileMenuOpen(false);
                }}
                className="text-emerald-700 font-medium"
              >
                Reset Demo
              </button>
            )}
          </div>
        </div>
      )}
    </header>
  );
};
