import { useEffect, useRef } from 'react';
import { animate, motion, useMotionValue, useReducedMotion, useTransform } from 'motion/react';
import { DURATION, EASE_OUT } from '../../utils/motion';
import { formatNumber } from '../../utils/formatters';

interface AnimatedNumberProps {
  value: number;
  decimals?: number;
  /** Seconds. Data transitions sit in the 250–400ms band. */
  duration?: number;
  /** Optional starting value for the very first render (e.g. count up on entry). */
  from?: number;
  className?: string;
  format?: (value: number) => string;
}

/**
 * Interpolates between values without re-rendering React on every frame: the
 * text node is driven directly by a Motion value. Screen readers get the final
 * value only.
 */
export function AnimatedNumber({
  value,
  decimals = 1,
  duration = DURATION.data,
  from,
  className,
  format,
}: AnimatedNumberProps) {
  const reduce = useReducedMotion();
  const fmt = format ?? ((v: number) => formatNumber(v, decimals));
  const motionValue = useMotionValue(reduce || from === undefined ? value : from);
  const text = useTransform(motionValue, (v) => fmt(v));
  const first = useRef(true);

  useEffect(() => {
    if (reduce) {
      motionValue.set(value);
      return;
    }
    const controls = animate(motionValue, value, {
      duration: first.current && from !== undefined ? Math.max(duration, 0.7) : duration,
      ease: EASE_OUT,
    });
    first.current = false;
    return () => controls.stop();
  }, [value, reduce, duration, from, motionValue]);

  return (
    <span className={className}>
      <span className="sr-only">{fmt(value)}</span>
      <motion.span aria-hidden="true">{text}</motion.span>
    </span>
  );
}
