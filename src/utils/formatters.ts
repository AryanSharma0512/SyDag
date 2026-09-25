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

/** "2026-05-01" → "May 1". Calendar dates are read as UTC so no time zone shifts the day. */
export function formatDay(isoDate: string): string {
  const d = new Date(`${isoDate.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? isoDate : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

/** ISO timestamp → "Sep 24, 2026" in the viewer's time zone. */
export function formatRetrieved(isoTimestamp: string): string {
  const d = new Date(isoTimestamp);
  return Number.isNaN(d.getTime()) ? isoTimestamp : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/** ISO timestamp → "Sep 24, 2026, 9:42 PM" in the viewer's time zone. */
export function formatRetrievedTime(isoTimestamp: string): string {
  const d = new Date(isoTimestamp);
  return Number.isNaN(d.getTime())
    ? isoTimestamp
    : d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
}
