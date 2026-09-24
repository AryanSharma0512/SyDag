import { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, MotionConfig } from 'motion/react';
import { Navigation } from './components/common/Navigation';
import { Footer } from './components/common/Footer';
import { PageTransition } from './components/common/PageTransition';
import { OverviewPage } from './components/overview/OverviewPage';
import { DashboardView } from './components/dashboard/DashboardView';
import { MethodologyPage } from './components/methodology/MethodologyPage';
import { AboutPage } from './components/about/AboutPage';
import { ROUTES, RouterProvider, routeFromPath, type Route } from './utils/router';
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

  // Unknown paths resolve to the overview.
  useEffect(() => {
    if (!routeFromPath(window.location.pathname)) {
      window.history.replaceState(null, '', `/${window.location.search}${window.location.hash}`);
    }
  }, []);

  const navigate = useCallback(
    (next: Route) => {
      if (next === route) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      window.history.pushState(null, '', `${ROUTES[next].path}${window.location.search}`);
      setRoute(next);
    },
    [route],
  );

  useEffect(() => {
    const onPopState = () => {
      setRoute(routeFromPath(window.location.pathname) ?? 'overview');
      setFlags(readFlags());
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
            <PageTransition key={route}>
              <main id="main">{page}</main>
            </PageTransition>
          </AnimatePresence>
          {!flags.presentation && <Footer />}
        </div>
      </RouterProvider>
    </MotionConfig>
  );
}
