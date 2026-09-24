/**
 * Formatting and Numeric Utilities
 * Ensures standardized scientific tabular formatting and smooth numeric transitions.
 */

export function formatYield(val: number): string {
  return Number.isFinite(val) ? val.toFixed(1) : '--';
}

export function formatPercent(val: number, includeSign: boolean = true): string {
  if (!Number.isFinite(val)) return '--';
  const prefix = includeSign && val > 0 ? '+' : '';
  return `${prefix}${val.toFixed(1)}%`;
}

export function formatConfidence(val: number): string {
  return Math.round(val).toString();
}

export function formatMm(val: number): string {
  return Math.round(val).toString();
}
