/**
 * Formatting utilities for scientific values shown across the interface.
 */

export function formatYield(val: number, decimals = 1): string {
  return Number.isFinite(val) ? val.toFixed(decimals) : '--';
}

export function formatSignedPercent(val: number, decimals = 1): string {
  if (!Number.isFinite(val)) return '--';
  const prefix = val > 0 ? '+' : val < 0 ? '−' : '';
  return `${prefix}${Math.abs(val).toFixed(decimals)}%`;
}

export function formatNumber(val: number, decimals = 0): string {
  if (!Number.isFinite(val)) return '--';
  return val.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** "Corn (Maize)" → "Corn" */
export function shortCropName(crop: string): string {
  return crop.split(' (')[0];
}

/** "HIGH" → "High" */
export function ratingLabel(rating: string): string {
  return rating.charAt(0) + rating.slice(1).toLowerCase();
}
