import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { APP_CONFIG } from '../../config/appConfig';
import { EASE_OUT } from '../../utils/motion';
import { BRAND_COLORS, MARK_PATHS, signalArc } from './SignalMark';

/** The intro plays once per page load, not on every remount of the navigation. */
let introPlayed = false;

const ECHO_FROM = signalArc(8.4, -24, -62);
const PULSE_TO = signalArc(14, -24, -62);

interface AnimatedLogoProps {
  size?: number;
  showWordmark?: boolean;
  wordmarkClassName?: string;
}

/**
 * First load (~1s): soil horizons draw left to right, the leaf grows from its
 * base, the signal arc sweeps over, the outer echo radiates and the wordmark
 * settles into place. Afterwards the mark is static; hovering emits one pulse.
 */
export function AnimatedLogo({ size = 28, showWordmark = true, wordmarkClassName = 'text-[17px]' }: AnimatedLogoProps) {
  const reduce = useReducedMotion();
  const [playIntro] = useState(() => !introPlayed);
  const [pulseKey, setPulseKey] = useState(0);

  useEffect(() => {
    introPlayed = true;
  }, []);

  const intro = playIntro && !reduce;
  const draw = (delay: number, opacity = 1) =>
    intro
      ? {
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity },
          transition: {
            pathLength: { delay, duration: 0.34, ease: EASE_OUT },
            opacity: { delay, duration: 0.08 },
          },
        }
      : { initial: false as const, animate: { pathLength: 1, opacity } };

  return (
    <span
      className="inline-flex items-center gap-2"
      onMouseEnter={() => {
        if (!reduce) setPulseKey((k) => k + 1);
      }}
    >
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" overflow="visible" aria-hidden="true">
        <motion.path
          d={MARK_PATHS.horizonTop}
          stroke={BRAND_COLORS.soil}
          strokeWidth={2.6}
          strokeLinecap="round"
          {...draw(0)}
        />
        <motion.path
          d={MARK_PATHS.horizonLow}
          stroke={BRAND_COLORS.soil}
          strokeWidth={2.6}
          strokeLinecap="round"
          {...draw(0.09, 0.5)}
        />
        <motion.path
          d={MARK_PATHS.leaf}
          fill={BRAND_COLORS.leaf}
          style={{ originX: 1, originY: 0.92 }}
          initial={intro ? { scale: 0.15, rotate: -22, opacity: 0 } : false}
          animate={{ scale: 1, rotate: 0, opacity: 1 }}
          transition={{ delay: 0.22, duration: 0.46, ease: EASE_OUT }}
        />
        <motion.path
          d={MARK_PATHS.arc}
          stroke={BRAND_COLORS.leaf}
          strokeWidth={2.7}
          strokeLinecap="round"
          {...draw(0.44)}
        />
        <motion.path
          stroke={BRAND_COLORS.leaf}
          strokeWidth={2.3}
          strokeLinecap="round"
          initial={intro ? { d: ECHO_FROM, opacity: 0 } : false}
          animate={{ d: MARK_PATHS.echo, opacity: 0.45 }}
          transition={{ delay: 0.68, duration: 0.36, ease: EASE_OUT }}
        />
        {pulseKey > 0 && (
          <motion.path
            key={pulseKey}
            stroke={BRAND_COLORS.leaf}
            strokeWidth={1.8}
            strokeLinecap="round"
            initial={{ d: MARK_PATHS.echo, opacity: 0.55 }}
            animate={{ d: PULSE_TO, opacity: 0 }}
            transition={{ duration: 0.35, ease: EASE_OUT }}
          />
        )}
      </svg>
      {showWordmark && (
        <motion.span
          className={`font-semibold tracking-[-0.02em] text-ink ${wordmarkClassName}`}
          initial={intro ? { opacity: 0, x: -6 } : false}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3, duration: 0.55, ease: EASE_OUT }}
        >
          {APP_CONFIG.name}
        </motion.span>
      )}
    </span>
  );
}
