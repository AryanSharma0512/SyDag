import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Menu, X } from 'lucide-react';
import { AnimatedLogo } from '../brand/AnimatedLogo';
import { DataBadge } from './DataBadge';
import { Link, ROUTE_ORDER, ROUTES, useRouter } from '../../utils/router';
import { EASE_OUT, GLIDE } from '../../utils/motion';

interface NavigationProps {
  isPresentationMode: boolean;
  onExitPresentation: () => void;
}

export function Navigation({ isPresentationMode, onExitPresentation }: NavigationProps) {
  const { route } = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 6);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    setMenuOpen(false);
  }, [route]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  const shell = `sticky top-0 z-40 border-b transition-[background-color,border-color,backdrop-filter] duration-300 ${
    scrolled || menuOpen ? 'border-line bg-canvas/85 backdrop-blur-md' : 'border-transparent bg-canvas'
  }`;

  if (isPresentationMode) {
    return (
      <header className={shell}>
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="overview" aria-label="SoilSignal overview" className="rounded-md">
            <AnimatedLogo size={24} wordmarkClassName="text-[16px]" />
          </Link>
          <button
            type="button"
            onClick={onExitPresentation}
            className="lift inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-[12px] font-medium text-muted hover:border-line-strong hover:text-ink"
          >
            Exit presentation
            <kbd className="data rounded border border-line bg-mist px-1 text-[11px] text-muted">F</kbd>
          </button>
        </div>
      </header>
    );
  }

  return (
    <header className={shell}>
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-10 px-4 sm:px-6">
        <Link to="overview" aria-label="SoilSignal overview" className="-mx-1 shrink-0 rounded-md px-1">
          <AnimatedLogo />
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-7 md:flex">
          {ROUTE_ORDER.map((r) => {
            const active = route === r;
            return (
              <Link
                key={r}
                to={r}
                aria-current={active ? 'page' : undefined}
                className={`relative py-2 text-[14px] transition-colors duration-150 ${
                  active ? 'font-medium text-ink' : 'text-muted hover:text-ink'
                }`}
              >
                {ROUTES[r].label}
                {active && (
                  <motion.span
                    layoutId="nav-underline"
                    className="absolute bottom-0 left-1/2 h-[2px] w-4 -translate-x-1/2 rounded-full bg-leaf-700"
                    transition={GLIDE}
                  />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <DataBadge variant="demo" className="hidden sm:inline-flex" />
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-controls="mobile-navigation"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            className="-mr-1 inline-flex h-10 w-10 items-center justify-center rounded-lg text-ink-soft hover:bg-mist md:hidden"
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {menuOpen && (
          <motion.nav
            id="mobile-navigation"
            aria-label="Primary"
            className="overflow-hidden border-t border-line md:hidden"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: EASE_OUT }}
          >
            <ul className="mx-auto max-w-6xl px-4 py-3 sm:px-6">
              {ROUTE_ORDER.map((r, i) => {
                const active = route === r;
                return (
                  <motion.li
                    key={r}
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.04 * i + 0.05, duration: 0.25, ease: EASE_OUT }}
                  >
                    <Link
                      to={r}
                      aria-current={active ? 'page' : undefined}
                      className={`flex items-center justify-between rounded-lg px-2 py-3 text-[17px] ${
                        active ? 'font-medium text-ink' : 'text-muted'
                      }`}
                    >
                      {ROUTES[r].label}
                      {active && <span className="h-1.5 w-1.5 rounded-full bg-leaf-700" aria-hidden="true" />}
                    </Link>
                  </motion.li>
                );
              })}
              <li className="mt-2 border-t border-line px-2 pt-4 pb-1">
                <DataBadge variant="demo" />
              </li>
            </ul>
          </motion.nav>
        )}
      </AnimatePresence>
    </header>
  );
}
