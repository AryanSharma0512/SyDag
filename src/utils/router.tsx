import { createContext, useContext, type AnchorHTMLAttributes, type MouseEvent, type ReactNode } from 'react';

/**
 * Minimal client-side routing for a handful of static destinations. Nginx (and the Vite
 * dev/preview servers) fall back to index.html, so every path can be opened directly.
 */

export type Route = 'overview' | 'dashboard' | 'data' | 'methodology' | 'about';

export const ROUTES: Record<Route, { path: string; label: string; title: string }> = {
  overview: { path: '/', label: 'Overview', title: 'SoilSignal · Know the season before harvest' },
  dashboard: { path: '/dashboard', label: 'Forecast', title: 'Yield forecast · SoilSignal' },
  data: { path: '/data', label: 'Data', title: 'Data · SoilSignal' },
  methodology: { path: '/methodology', label: 'Methodology', title: 'Methodology · SoilSignal' },
  about: { path: '/about', label: 'About', title: 'About · SoilSignal' },
};

export const ROUTE_ORDER: Route[] = ['overview', 'dashboard', 'methodology', 'data', 'about'];

export function routeFromPath(pathname: string): Route | null {
  const normalized = pathname.replace(/\/+$/, '').toLowerCase() || '/';
  return ROUTE_ORDER.find((route) => ROUTES[route].path === normalized) ?? null;
}

/** Query parameters to set (a string) or remove (null) along with the route change. */
export type RouteQuery = Record<string, string | null>;

type Navigate = (route: Route, query?: RouteQuery) => void;

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

/** The current query string with `query` applied, for building links. */
export function searchWith(query?: RouteQuery): string {
  const params = new URLSearchParams(window.location.search);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === null) params.delete(key);
    else params.set(key, value);
  }
  const text = params.toString();
  return text ? `?${text}` : '';
}

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { to: Route; query?: RouteQuery };

/** An anchor that navigates client-side but keeps native behaviour for new-tab clicks. */
export function Link({ to, query, onClick, children, ...rest }: LinkProps) {
  const { navigate } = useRouter();
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    navigate(to, query);
  };
  return (
    <a href={`${ROUTES[to].path}${searchWith(query)}`} onClick={handleClick} {...rest}>
      {children}
    </a>
  );
}
