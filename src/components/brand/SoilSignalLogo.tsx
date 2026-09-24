import { APP_CONFIG } from '../../config/appConfig';
import { SignalMark } from './SignalMark';

interface SoilSignalLogoProps {
  size?: number;
  className?: string;
  wordmarkClassName?: string;
  showWordmark?: boolean;
}

/** Static lockup: mark + wordmark. Used in the footer and presentation surfaces. */
export function SoilSignalLogo({
  size = 26,
  className = '',
  wordmarkClassName = 'text-[17px]',
  showWordmark = true,
}: SoilSignalLogoProps) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <SignalMark size={size} title={showWordmark ? undefined : APP_CONFIG.name} />
      {showWordmark && (
        <span className={`font-semibold tracking-[-0.02em] text-ink ${wordmarkClassName}`}>{APP_CONFIG.name}</span>
      )}
    </span>
  );
}
