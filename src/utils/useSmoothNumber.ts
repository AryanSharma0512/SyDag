import { useEffect, useRef, useState } from 'react';

/**
 * Hook to smoothly interpolate a numeric value over a given duration (default ~300ms)
 * using requestAnimationFrame with ease-out cubic curve.
 */
export function useSmoothNumber(targetValue: number, durationMs: number = 320, decimals: number = 1): number {
  const [currentValue, setCurrentValue] = useState(targetValue);
  const startValRef = useRef(targetValue);
  const targetValRef = useRef(targetValue);
  const startTimeRef = useRef<number | null>(null);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    // If target changed, initiate smooth transition
    if (targetValRef.current !== targetValue) {
      startValRef.current = currentValue;
      targetValRef.current = targetValue;
      startTimeRef.current = null;

      const easeOutCubic = (t: number): number => {
        return 1 - Math.pow(1 - t, 3);
      };

      const animate = (timestamp: number) => {
        if (!startTimeRef.current) startTimeRef.current = timestamp;
        const elapsed = timestamp - startTimeRef.current;
        const progress = Math.min(elapsed / durationMs, 1);
        const easedProgress = easeOutCubic(progress);

        const nextVal = startValRef.current + (targetValRef.current - startValRef.current) * easedProgress;
        
        // Round to desired decimal precision
        const factor = Math.pow(10, decimals);
        setCurrentValue(Math.round(nextVal * factor) / factor);

        if (progress < 1) {
          animFrameRef.current = requestAnimationFrame(animate);
        } else {
          setCurrentValue(targetValRef.current);
        }
      };

      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
      animFrameRef.current = requestAnimationFrame(animate);
    }

    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [targetValue, durationMs, decimals, currentValue]);

  return currentValue;
}
