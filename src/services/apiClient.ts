/**
 * Minimal JSON client for the SoilSignal API.
 * Services call this only when APP_CONFIG.demoMode is off; components never import it.
 */

import { APP_CONFIG } from '../config/appConfig';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${APP_CONFIG.apiBaseUrl}${path}`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.detail ?? `GET ${path} failed with ${res.status}`);
  }
  return res.json() as Promise<T>;
}

/** A file download (e.g. CSV). Errors carry the API's `detail` message, as with apiGet. */
export async function apiGetFile(path: string): Promise<Blob> {
  const res = await fetch(`${APP_CONFIG.apiBaseUrl}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.detail ?? `GET ${path} failed with ${res.status}`);
  }
  return res.blob();
}
