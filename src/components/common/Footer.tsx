import { APP_CONFIG, EVENT_CONTEXT } from '../../config/appConfig';
import { Link, ROUTE_ORDER, ROUTES } from '../../utils/router';
import { SoilSignalLogo } from '../brand/SoilSignalLogo';

export function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 sm:px-6 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
          <SoilSignalLogo size={22} wordmarkClassName="text-[15px]" />
          <span className="text-[13px] text-muted">{APP_CONFIG.tagline}</span>
        </div>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-5 gap-y-2 text-[13px] text-muted">
          {ROUTE_ORDER.map((r) => (
            <Link key={r} to={r} className="hover:text-ink">
              {ROUTES[r].label}
            </Link>
          ))}
        </nav>
        <p className="text-[13px] text-muted">
          {EVENT_CONTEXT.name} · {EVENT_CONTEXT.host} · <span className="data">v{APP_CONFIG.version}</span>
        </p>
      </div>
    </footer>
  );
}
