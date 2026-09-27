/**
 * Application Configuration
 * Centralized branding and demo settings.
 */

export const APP_CONFIG = {
  name: 'SoilSignal',
  tagline: 'Know the season before harvest.',
  subtitle:
    'SoilSignal uses satellite imagery, field records and weather history to estimate final maize yield during the growing season.',
  version: '1.0.0-hackathon',
  datasetLabel: 'Demo Data',
  // Build with VITE_DEMO_MODE=false to fetch from the SoilSignal API instead of src/mock.
  demoMode: import.meta.env.VITE_DEMO_MODE !== 'false',
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api',
  defaultFieldId: 'purdue-104',
  // Forecast date the live models open on (index into a plot's forecast dates): mid-season,
  // before harvest. The final results open on their own earliest useful stage instead.
  defaultDateIndex: 2,
  seasonYear: 2026,
  // Validation MAE (bu/ac) the team treats as good enough to act on. Unset until the team
  // agrees one; when set, the model reliability chart draws it as a reference line.
  acceptableMaeBuAc: null as number | null,
};

export const EVENT_CONTEXT = {
  name: 'SyDAg26 IoT4Ag Hackathon',
  host: 'Purdue University',
};

export interface TeamMember {
  name: string;
  initials: string;
  /** Leave unset until confirmed; the card keeps the line's space so every card stays the same size. */
  degree?: string;
  /** Profile photo under /public; the initials show until one is set. */
  photo?: string;
  /** CSS object-position for the photo crop. */
  photoPosition?: string;
}

export const TEAM: TeamMember[] = [
  { name: 'Aryan Sharma', initials: 'AS', degree: 'B.S. Agriculture', photo: '/team/aryan-sharma.jpg', photoPosition: '50% 20%' },
  { name: 'Sahil Jain', initials: 'SJ', degree: 'B.S. Computer Science', photo: '/team/sahil-jain.webp' },
  { name: 'Shashwat Goel', initials: 'SG', degree: 'B.S. Computer Science', photo: '/team/shashwat-goel.webp' },
  { name: 'Sri Madur', initials: 'SM', degree: 'B.S. Mathematics' },
  { name: 'Sidney Millen', initials: 'SM', degree: 'B.S. Cybersecurity', photo: '/team/sidney-millen.webp' },
];
