import { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, MotionConfig } from 'motion/react';
import { Navigation } from './components/common/Navigation';
import { Footer } from './components/common/Footer';
import { PageTransition } from './components/common/PageTransition';
import { OverviewPage } from './components/overview/OverviewPage';
import { DashboardView } from './components/dashboard/DashboardView';
import { DataExplorerPage } from './components/data/DataExplorerPage';
import { MethodologyPage } from './components/methodology/MethodologyPage';
import { AboutPage } from './components/about/AboutPage';
import { ROUTES, RouterProvider, routeFromPath, searchWith, type Route, type RouteQuery } from './utils/router';
import { isTypingTarget } from './utils/hooks';

interface Flags {
  presentation: boolean;
  debug: boolean;
}

function readFlags(): Flags {
  const params = new URLSearchParams(window.location.search);
  return {
    presentation: params.get('presentation') === 'true',
    debug: params.get('debug') === 'true',
  };
}

export default function App() {
  const [route, setRoute] = useState<Route>(() => routeFromPath(window.location.pathname) ?? 'overview');
  const [flags, setFlags] = useState<Flags>(readFlags);
  const [visit, setVisit] = useState(0);

  // Unknown paths resolve to the overview.
  useEffect(() => {
    if (!routeFromPath(window.location.pathname)) {
      window.history.replaceState(null, '', `/${window.location.search}${window.location.hash}`);
    }
  }, []);

  const navigate = useCallback(
    (next: Route, query?: RouteQuery) => {
      if (next === route && !query) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      window.history.pushState(null, '', `${ROUTES[next].path}${searchWith(query)}`);
      setRoute(next);
      // Same page, new query (e.g. another site): remount so the page reads it afresh.
      if (next === route) setVisit((n) => n + 1);
    },
    [route],
  );

  useEffect(() => {
    const onPopState = () => {
      setRoute(routeFromPath(window.location.pathname) ?? 'overview');
      setFlags(readFlags());
      setVisit((n) => n + 1);
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    document.title = ROUTES[route].title;
  }, [route]);

  // Keep ?presentation=true in sync with the mode so the URL can be shared.
  useEffect(() => {
    const url = new URL(window.location.href);
    if (flags.presentation) url.searchParams.set('presentation', 'true');
    else url.searchParams.delete('presentation');
    if (url.href !== window.location.href) window.history.replaceState(null, '', url);
  }, [flags.presentation]);

  const togglePresentation = useCallback(() => {
    setFlags((current) => ({ ...current, presentation: !current.presentation }));
  }, []);

  // Quiet shortcut for presenters: F toggles presentation mode.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTypingTarget(event.target)) return;
      if (event.key === 'f' || event.key === 'F') {
        event.preventDefault();
        togglePresentation();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [togglePresentation]);

  let page;
  switch (route) {
    case 'dashboard':
      page = (
        <DashboardView
          isPresentationMode={flags.presentation}
          isDebugMode={flags.debug}
          onTogglePresentationMode={togglePresentation}
        />
      );
      break;
    case 'data':
      page = <DataExplorerPage />;
      break;
    case 'methodology':
      page = <MethodologyPage />;
      break;
    case 'about':
      page = <AboutPage />;
      break;
    default:
      page = <OverviewPage />;
  }

  return (
    <MotionConfig reducedMotion="user">
      <RouterProvider route={route} navigate={navigate}>
        <div className="flex min-h-screen flex-col bg-canvas text-ink">
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:shadow-lift"
          >
            Skip to content
          </a>
          <Navigation isPresentationMode={flags.presentation} onExitPresentation={togglePresentation} />
          <AnimatePresence mode="wait" onExitComplete={() => window.scrollTo(0, 0)}>
            <PageTransition key={`${route}-${visit}`}>
              <main id="main">{page}</main>
            </PageTransition>
          </AnimatePresence>
          {!flags.presentation && <Footer />}
        </div>
      </RouterProvider>
    </MotionConfig>
  );
}
