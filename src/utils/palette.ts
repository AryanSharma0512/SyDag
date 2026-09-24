/**
 * Hex mirror of the design tokens in index.css, for SVG drawing and for color
 * values Motion interpolates. Keep in sync with the @theme block.
 */
export const PALETTE = {
  canvas: '#F8F7F3',
  surface: '#FFFFFF',
  mist: '#F1EFE9',
  line: '#E8E5DD',
  lineStrong: '#D6D2C8',
  ink: '#14202B',
  inkSoft: '#2E3A46',
  muted: '#5B6674',
  faint: '#8C949F',
  leaf50: '#EEF6F2',
  leaf100: '#DCEEE5',
  leaf200: '#B7DBC8',
  leaf300: '#86C0A3',
  leaf400: '#4E9F7D',
  leaf500: '#1E8561',
  leaf600: '#0E7A56',
  leaf700: '#086C4C',
  leaf800: '#06573D',
  leaf900: '#05432F',
  soil50: '#FAF4EE',
  soil100: '#F3E6DA',
  soil200: '#E6CCB4',
  soil300: '#D3A882',
  soil400: '#BC8758',
  soil500: '#A66A3F',
  soil600: '#8C5733',
  soil700: '#6F4428',
  rain100: '#DFE9F2',
  rain300: '#9DBAD4',
  rain500: '#4F7DA8',
  rain600: '#3F6A93',
  sun100: '#F5E8CF',
  sun300: '#E2BF7C',
  sun500: '#C08A2E',
  sun700: '#7E581B',
  stress100: '#F3DEDA',
  stress300: '#DB9D93',
  stress500: '#B8574A',
  stress600: '#9C4538',
} as const;

/** Linear blend between two hex colors (t in 0..1). */
export function mixHex(a: string, b: string, t: number): string {
  const pa = parseInt(a.slice(1), 16);
  const pb = parseInt(b.slice(1), 16);
  const k = Math.max(0, Math.min(1, t));
  const channel = (shift: number) => {
    const ca = (pa >> shift) & 255;
    const cb = (pb >> shift) & 255;
    return Math.round(ca + (cb - ca) * k);
  };
  const hex = (channel(16) << 16) | (channel(8) << 8) | channel(0);
  return `#${hex.toString(16).padStart(6, '0')}`;
}

/** Piecewise blend across several color stops placed evenly on 0..1. */
export function rampColor(stops: readonly string[], t: number): string {
  const k = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(k));
  return mixHex(stops[i], stops[i + 1], k - i);
}
