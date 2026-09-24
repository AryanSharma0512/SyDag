/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from 'react';
import { Navigation } from './components/common/Navigation';
import { LandingPage } from './components/landing/LandingPage';
import { DashboardView } from './components/dashboard/DashboardView';
import { AboutPage } from './components/about/AboutPage';

type Route = 'landing' | 'dashboard' | 'about';

export default function App() {
  // Read initial route and presentation flag from browser URL
  const [currentRoute, setCurrentRoute] = useState<Route>(() => {
    const path = window.location.pathname.toLowerCase();
    if (path.includes('dashboard')) return 'dashboard';
    if (path.includes('about') || path.includes('methodology')) return 'about';
    // Default directly to dashboard if requested or if root
    // For IoT4Ag hackathon evaluation, default to dashboard if search params exist or user lands directly
    return 'dashboard';
  });

  const [isPresentationMode, setIsPresentationMode] = useState<boolean>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('presentation') === 'true';
  });

  // Sync route changes with browser history
  const handleRouteChange = (newRoute: Route) => {
    setCurrentRoute(newRoute);
    const path = newRoute === 'landing' ? '/' : `/${newRoute}`;
    const query = isPresentationMode ? '?presentation=true' : '';
    window.history.pushState({}, '', `${path}${query}`);
  };

  const handleTogglePresentation = () => {
    setIsPresentationMode((prev) => {
      const next = !prev;
      const url = new URL(window.location.href);
      if (next) {
        url.searchParams.set('presentation', 'true');
      } else {
        url.searchParams.delete('presentation');
      }
      window.history.replaceState({}, '', url.toString());
      return next;
    });
  };

  // Listen to popstate (browser back/forward)
  useEffect(() => {
    const handlePopState = () => {
      const path = window.location.pathname.toLowerCase();
      if (path.includes('about') || path.includes('methodology')) {
        setCurrentRoute('about');
      } else if (path.includes('landing') || path === '/') {
        setCurrentRoute('landing');
      } else {
        setCurrentRoute('dashboard');
      }
      const params = new URLSearchParams(window.location.search);
      setIsPresentationMode(params.get('presentation') === 'true');
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  return (
    <div className="min-h-screen bg-[#FBFBFA] text-slate-900 font-sans antialiased selection:bg-emerald-100 selection:text-emerald-900">
      {/* Top Navigation */}
      <Navigation
        currentRoute={currentRoute}
        onRouteChange={handleRouteChange}
        isPresentationMode={isPresentationMode}
        onTogglePresentationMode={handleTogglePresentation}
      />

      {/* Main Route View */}
      {currentRoute === 'landing' && (
        <LandingPage
          onNavigateToDashboard={() => handleRouteChange('dashboard')}
          onNavigateToAbout={() => handleRouteChange('about')}
        />
      )}

      {currentRoute === 'dashboard' && (
        <DashboardView
          isPresentationMode={isPresentationMode}
          onTogglePresentationMode={handleTogglePresentation}
        />
      )}

      {currentRoute === 'about' && (
        <AboutPage
          onNavigateToDashboard={() => handleRouteChange('dashboard')}
        />
      )}
    </div>
  );
}
