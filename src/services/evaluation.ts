/**
 * Model Evaluation Service
 * Validation results for the deployed models (GET /api/models) and the ML team's
 * with/without-imagery comparison (GET /api/evaluation/imagery). The demo build has
 * no trained models, so it reports none rather than inventing metrics.
 */

import type { ImageryAblation, ModelInfo } from '../types/agricultural';
import { APP_CONFIG } from '../config/appConfig';
import { apiGet } from './apiClient';

export async function getModels(): Promise<ModelInfo[]> {
  if (APP_CONFIG.demoMode) return [];
  return apiGet<ModelInfo[]>('/models');
}

export async function getImageryAblation(): Promise<ImageryAblation> {
  if (APP_CONFIG.demoMode) return { status: 'pending', variants: [] };
  return apiGet<ImageryAblation>('/evaluation/imagery');
}
