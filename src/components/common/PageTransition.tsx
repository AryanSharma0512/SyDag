import { useEffect, useState, type ReactNode } from 'react';
import { motion } from 'motion/react';
import { DURATION, EASE_OUT } from '../../utils/motion';

/** The first page of a visit has its own entrance choreography, so only later routes fade in. */
let hasMounted = false;

/**
 * Route entrance: a quiet fade with 8px of rise. Exits are quicker than entries
 * so navigation never feels like it waits. With reduced motion, Motion drops the
 * transform and only the fade remains.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const [firstVisit] = useState(() => !hasMounted);

  useEffect(() => {
    hasMounted = true;
  }, []);

  return (
    <motion.div
      className="flex-1"
      initial={firstVisit ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, transition: { duration: 0.14, ease: 'easeOut' } }}
      transition={{ duration: DURATION.base, ease: EASE_OUT }}
    >
      {children}
    </motion.div>
  );
}
