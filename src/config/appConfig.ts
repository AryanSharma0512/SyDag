/**
 * Application Configuration
 * Centralized branding and demo settings.
 */

export const APP_CONFIG = {
  name: 'SoilSignal',
  tagline: 'See the season before harvest.',
  subtitle:
    'Progressive crop yield forecasting powered by field observations, environmental context, and interpretable models.',
  version: '1.0.0-hackathon',
  datasetLabel: 'Demo Data',
  demoMode: true,
  defaultFieldId: 'purdue-104',
  defaultDateIndex: 4,
  seasonYear: 2026,
};

export const EVENT_CONTEXT = {
  name: 'SyDAg26 IoT4Ag Hackathon',
  host: 'Purdue University',
};

export interface TeamMember {
  name: string;
  initials: string;
  degree: string;
}

export const TEAM: TeamMember[] = [
  { name: 'Aryan Sharma', initials: 'AS', degree: 'B.S. Agriculture' },
  { name: 'Sahil Jain', initials: 'SJ', degree: 'B.S. Computer Science' },
  { name: 'Shashwat Goel', initials: 'SG', degree: 'B.S. Computer Science' },
];
