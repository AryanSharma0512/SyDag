import { createContext, useContext, type AnchorHTMLAttributes, type MouseEvent, type ReactNode } from 'react';

/**
 * Minimal client-side routing for four static destinations. Nginx (and the Vite
 * dev/preview servers) fall back to index.html, so every path can be opened directly.
 */

export type Route = 'overview' | 'dashboard' | 'methodology' | 'about';

export const ROUTES: Record<Route, { path: string; label: string; title: string }> = {
  overview: { path: '/', label: 'Overview', title: 'SoilSignal · See the season before harvest' },
  dashboard: { path: '/dashboard', label: 'Dashboard', title: 'Dashboard · SoilSignal' },
  methodology: { path: '/methodology', label: 'Methodology', title: 'Methodology · SoilSignal' },
  about: { path: '/about', label: 'About', title: 'About · SoilSignal' },
};

export const ROUTE_ORDER: Route[] = ['overview', 'dashboard', 'methodology', 'about'];

export function routeFromPath(pathname: string): Route | null {
  const normalized = pathname.replace(/\/+$/, '').toLowerCase() || '/';
  return ROUTE_ORDER.find((route) => ROUTES[route].path === normalized) ?? null;
}

type Navigate = (route: Route) => void;

const RouterContext = createContext<{ route: Route; navigate: Navigate }>({
  route: 'overview',
  navigate: () => undefined,
});

export function RouterProvider({ route, navigate, children }: { route: Route; navigate: Navigate; children: ReactNode }) {
  return <RouterContext.Provider value={{ route, navigate }}>{children}</RouterContext.Provider>;
}

export function useRouter() {
  return useContext(RouterContext);
}

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { to: Route };

/** An anchor that navigates client-side but keeps native behaviour for new-tab clicks. */
export function Link({ to, onClick, children, ...rest }: LinkProps) {
  const { navigate } = useRouter();
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    navigate(to);
  };
  return (
    <a href={`${ROUTES[to].path}${window.location.search}`} onClick={handleClick} {...rest}>
      {children}
    </a>
  );
}
