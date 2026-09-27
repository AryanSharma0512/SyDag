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

/**
 * Short labels for a site's canonical plot ids, for display only: "2022_Ames_4233_18_10"
 * → "4233-18-10". The season and site prefix goes, as does a trial name every plot at the
 * site shares ("2022_Lincoln_hybrids_10_10" → "10-10"); a trial name that tells plots
 * apart stays ("2022_Scottsbluff_n150_10_11" → "n150 · 10-11"). Ids in another form pass
 * through unchanged.
 */
export function shortPlotIds(plotIds: string[], site: string): Map<string, string> {
  const prefix = new RegExp(`^\\d{4}_${site.replace(/[^A-Za-z0-9]/g, '')}_`, 'i');
  const parts = plotIds.map((id) => (prefix.test(id) ? id.replace(prefix, '').split('_') : null));
  const lead = parts[0]?.[0];
  const shared =
    lead !== undefined && !/^\d+$/.test(lead) && parts.every((p) => p !== null && p.length > 1 && p[0] === lead);
  return new Map(
    plotIds.map((id, i) => {
      const tokens = parts[i];
      if (!tokens) return [id, id];
      const rest = shared ? tokens.slice(1) : tokens;
      const named = rest.length > 1 && !/^\d+$/.test(rest[0]);
      return [id, named ? `${rest[0]} · ${rest.slice(1).join('-')}` : rest.join('-')];
    }),
  );
}
