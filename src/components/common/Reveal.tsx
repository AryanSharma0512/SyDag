import type { ReactNode } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { DURATION, EASE_OUT } from '../../utils/motion';

interface RevealProps {
  children: ReactNode;
  className?: string;
  delay?: number;
  /** Vertical travel in px. Kept small on purpose. */
  distance?: number;
  as?: 'div' | 'section' | 'li' | 'header';
}

/**
 * Reveals a semantic section as it enters the viewport: opacity, a small rise,
 * and a 0.99 → 1 scale. Runs once. Reduced-motion users get the final state.
 */
export function Reveal({ children, className, delay = 0, distance = 14, as = 'div' }: RevealProps) {
  const reduce = useReducedMotion();
  const Component = motion[as];
  return (
    <Component
      className={className}
      initial={reduce ? false : { opacity: 0, y: distance, scale: 0.99 }}
      whileInView={{ opacity: 1, y: 0, scale: 1 }}
      viewport={{ once: true, margin: '0px 0px -10% 0px' }}
      transition={{ duration: DURATION.reveal, ease: EASE_OUT, delay }}
    >
      {children}
    </Component>
  );
}
