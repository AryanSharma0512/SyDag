/**
 * Application Configuration
 * Centralized branding and demo settings so the application can be renamed or reconfigured instantly.
 */

export const APP_CONFIG = {
  name: 'YieldLens',
  tagline: 'Precision Crop Yield Forecasting & Agricultural Intelligence',
  subtitle: 'Understand where yield is heading, how confident the forecast is, and what is influencing it.',
  version: '1.0.0-hackathon',
  datasetLabel: 'Demo Dataset', // Will become 'Purdue 2026 Dataset' when competition data arrives
  demoMode: true,
  defaultFieldId: 'purdue-104',
  defaultDateIndex: 4, // July 22, 2026
  seasonYear: 2026,
  supportedCrops: ['Corn (Maize)', 'Soybeans', 'Winter Wheat'],
  contactEmail: 'iot4ag-team@hackathon.org',
};
