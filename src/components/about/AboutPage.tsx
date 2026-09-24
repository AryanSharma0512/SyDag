import { useEffect, useMemo, useRef } from 'react';
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform, type MotionValue } from 'motion/react';
import { ArrowRight } from 'lucide-react';
import { EVENT_CONTEXT } from '../../config/appConfig';
import { monotonePath, type Pt } from '../../utils/chart';
import { EASE_OUT } from '../../utils/motion';
import { useIsMobile } from '../../utils/hooks';
import { PALETTE as C } from '../../utils/palette';
import { Link } from '../../utils/router';
import { Team } from './Team';

const W = 1200;
const H = 760;
const SPACING = 76;

function contourY(k: number, x: number) {
  return 60 + k * SPACING + 14 * Math.sin(x / 180 + k * 0.8) + 7 * Math.sin(x / 73 + k * 1.9);
}

/** One contour. It eases a few pixels toward the pointer when the pointer is nearest to it. */
function Contour({ k, pointerY }: { k: number; pointerY: MotionValue<number> }) {
  const d = useMemo(() => {
    const pts: Pt[] = [];
    for (let x = -40; x <= W + 40; x += 80) pts.push({ x, y: contourY(k, x) });
    return monotonePath(pts);
  }, [k]);
  const baseY = 60 + k * SPACING;
  const target = useTransform(pointerY, (p) => {
    const delta = p - baseY;
    return Math.abs(delta) < SPACING / 2 ? Math.max(-9, Math.min(9, delta * 0.28)) : 0;
  });
  const y = useSpring(target, { stiffness: 70, damping: 18, mass: 0.8 });

  return (
    <motion.path
      d={d}
      fill="none"
      stroke={C.leaf900}
      strokeOpacity={0.075}
      strokeWidth={1}
      vectorEffect="non-scaling-stroke"
      style={{ y }}
    />
  );
}

/** Background: a quiet agricultural data field of topographic contours and tiny signal nodes. */
function ContourField() {
  const reduce = useReducedMotion();
  const isMobile = useIsMobile();
  const ref = useRef<HTMLDivElement>(null);
  const pointerY = useMotionValue(-1000);
  const interactive = !reduce && !isMobile;

  useEffect(() => {
    if (!interactive) return;
    const onMove = (event: PointerEvent) => {
      const rect = ref.current?.getBoundingClientRect();
      if (!rect) return;
      pointerY.set(((event.clientY - rect.top) / rect.height) * H);
    };
    const onLeave = () => pointerY.set(-1000);
    window.addEventListener('pointermove', onMove, { passive: true });
    document.documentElement.addEventListener('pointerleave', onLeave);
    return () => {
      window.removeEventListener('pointermove', onMove);
      document.documentElement.removeEventListener('pointerleave', onLeave);
    };
  }, [interactive, pointerY]);

  const nodes = useMemo(
    () =>
      // Placed in open space so no node ever sits behind text.
      [
        [280, 0],
        [1000, 1],
        [1120, 3],
        [60, 4],
        [1150, 5],
        [40, 7],
        [620, 8],
        [900, 9],
      ].map(([x, k], i) => ({ key: i, left: (x / W) * 100, top: (contourY(k, x) / H) * 100, delay: (i * 1.3) % 7 })),
    [],
  );

  return (
    <div ref={ref} className="pointer-events-none absolute inset-x-0 top-0 h-[760px] overflow-hidden" aria-hidden="true">
      <motion.svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.4, ease: 'easeOut' }}
      >
        {Array.from({ length: 10 }, (_, k) => (
          <Contour key={k} k={k} pointerY={pointerY} />
        ))}
      </motion.svg>
      {nodes.map((n) => (
        <span
          key={n.key}
          className={`absolute hidden h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-leaf-400 md:block ${reduce ? 'opacity-40' : 'ss-breathe'}`}
          style={{ left: `${n.left}%`, top: `${n.top}%`, animationDelay: `${n.delay}s` }}
        />
      ))}
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent to-canvas" />
    </div>
  );
}

export function AboutPage() {
  const reduce = useReducedMotion();
  const rise = (delay: number) => ({
    initial: reduce ? (false as const) : { opacity: 0, y: 10 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.6, ease: EASE_OUT, delay },
  });

  return (
    <div className="relative">
      <ContourField />
      <div className="relative mx-auto max-w-6xl px-4 pb-28 sm:px-6">
        <header className="max-w-3xl pt-16 pb-16 sm:pt-24 sm:pb-20">
          <motion.p className="text-[13px] font-medium text-leaf-700" {...rise(0)}>
            About
          </motion.p>
          <motion.h1
            className="mt-3 text-[40px] leading-[1.05] font-semibold tracking-[-0.035em] text-balance text-ink sm:text-[54px]"
            {...rise(0.05)}
          >
            The team behind SoilSignal
          </motion.h1>
          <motion.p className="mt-5 text-[17px] leading-relaxed text-pretty text-muted sm:text-[18px]" {...rise(0.12)}>
            SoilSignal is being developed for the {EVENT_CONTEXT.name} at {EVENT_CONTEXT.host}, exploring how crop
            observations and environmental context can become earlier, more interpretable yield forecasts.
          </motion.p>
        </header>

        <Team />

        <motion.div
          className="mt-24 flex flex-col items-start justify-between gap-6 border-t border-line pt-10 sm:flex-row sm:items-center"
          initial={reduce ? false : { opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.3 }}
        >
          <p className="max-w-md text-[15px] leading-relaxed text-muted">
            See how the forecast moves through a season, or read how the pieces fit together.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              to="dashboard"
              className="lift group inline-flex items-center gap-2 rounded-full bg-leaf-700 px-5 py-2.5 text-[15px] font-medium text-white hover:bg-leaf-800 hover:shadow-lift"
            >
              Explore Forecast
              <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
            </Link>
            <Link
              to="methodology"
              className="lift inline-flex items-center rounded-full border border-line-strong bg-surface px-5 py-2.5 text-[15px] font-medium text-ink hover:border-faint"
            >
              How It Works
            </Link>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
