import { APP_CONFIG } from '../../config/appConfig';

type BadgeVariant = 'demo' | 'challenge' | 'candidate' | 'illustrative';

const VARIANTS: Record<BadgeVariant, { label: string; dot: string; tone: string }> = {
  demo: {
    label: APP_CONFIG.datasetLabel,
    dot: 'bg-soil-500',
    tone: 'border-line bg-surface/80 text-ink-soft',
  },
  challenge: {
    label: 'Challenge-provided',
    dot: 'bg-leaf-600',
    tone: 'border-leaf-200 bg-leaf-50 text-leaf-800',
  },
  candidate: {
    label: 'Candidate',
    dot: 'border border-faint bg-transparent',
    tone: 'border-line bg-surface text-muted',
  },
  illustrative: {
    label: 'Illustrative Demo Layer',
    dot: 'bg-sun-500',
    tone: 'border-line bg-surface/90 text-ink-soft',
  },
};

interface DataBadgeProps {
  variant: BadgeVariant;
  label?: string;
  className?: string;
}

/** Small provenance chip. Always pairs a dot with a text label, never color alone. */
export function DataBadge({ variant, label, className = '' }: DataBadgeProps) {
  const v = VARIANTS[variant];
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-[3px] text-[12px] font-medium leading-5 ${v.tone} ${className}`}
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${v.dot}`} aria-hidden="true" />
      {label ?? v.label}
    </span>
  );
}
