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
  // What the site's numbers come from when the published results do not name it.
  datasetLabel: 'SyDAg 2022 maize trials',
  // The demo build (bundled sample data, no API) says so instead, so it is never mistaken for the results.
  demoBuildLabel: 'Demo build · sample data',
  // Build with VITE_DEMO_MODE=false to fetch from the SoilSignal API instead of src/mock.
  demoMode: import.meta.env.VITE_DEMO_MODE !== 'false',
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api',
  // Field the demo build and the live-model views open on, when their dataset has it.
  defaultFieldId: 'purdue-104',
  // Forecast date the live models open on (index into a plot's forecast dates): mid-season,
  // before harvest. The final results open on their own earliest useful stage instead.
  defaultDateIndex: 2,
  seasonYear: 2022,
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
  /** Role on the team, shown under the name. */
  role: string;
  degree?: string;
  /** Profile photo under /public; the initials show until one is set. */
  photo?: string;
  /** CSS object-position for the photo crop. */
  photoPosition?: string;
}

export const TEAM: TeamMember[] = [
  { name: 'Aryan Sharma', initials: 'AS', role: 'Team lead & backend guru', degree: 'B.S. Agriculture', photo: '/team/aryan-sharma.jpg', photoPosition: '50% 20%' },
  { name: 'Sri Madur', initials: 'SM', role: 'ML wizard', degree: 'B.S. Mathematics', photo: '/team/sri-madur.webp' },
  { name: 'Sahil Jain', initials: 'SJ', role: 'Frontend nerd', degree: 'B.S. Computer Science', photo: '/team/sahil-jain.webp' },
  { name: 'Shashwat Goel', initials: 'SG', role: 'Pipeline tester', degree: 'B.S. Computer Science', photo: '/team/shashwat-goel.webp' },
  { name: 'Sidney Millen', initials: 'SM', role: 'Security specialist & firewall whisperer', degree: 'B.S. Cybersecurity', photo: '/team/sidney-millen.webp' },
];
