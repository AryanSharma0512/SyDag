import { useEffect, useLayoutEffect, useRef, useState } from 'react';

/** Tracks a CSS media query. The initial value is read synchronously so the first render is correct. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window === 'undefined' ? false : window.matchMedia(query).matches,
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}

/** Below ~768px the motion system switches to its simplified mobile variants. */
export function useIsMobile(): boolean {
  return useMediaQuery('(max-width: 767px)');
}

/** Measures an element's content width and keeps it updated. */
export function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.getBoundingClientRect().width);
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) setWidth(entry.contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, width] as const;
}

/** Calls the handler when a pointer or focus event lands outside the element. */
export function useDismiss<T extends HTMLElement>(open: boolean, onDismiss: () => void) {
  const ref = useRef<T>(null);
  const handler = useRef(onDismiss);
  handler.current = onDismiss;

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) handler.current();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') handler.current();
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return ref;
}

/** True when the keyboard event originates from a text-entry control. */
export function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable;
}
