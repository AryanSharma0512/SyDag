/**
 * Shared motion vocabulary. Every animated surface in SoilSignal draws from
 * these values so entrances, data transitions and micro-interactions feel like
 * one system.
 */

export const EASE_OUT = [0.22, 1, 0.36, 1] as const;

export const DURATION = {
  /** Hover feedback, fades on small elements. */
  micro: 0.15,
  /** Route transitions, tab switches. */
  base: 0.25,
  /** Numbers, bars and chart geometry reacting to new data. */
  data: 0.38,
  /** Section reveals on scroll. */
  reveal: 0.6,
} as const;

/** A calm spring for markers and indicators that glide to a new position. */
export const GLIDE = { type: 'spring', stiffness: 260, damping: 32, mass: 0.9 } as const;

/** Data transition used for synchronized updates while scrubbing the season. */
export const DATA_TRANSITION = { duration: DURATION.data, ease: EASE_OUT } as const;
