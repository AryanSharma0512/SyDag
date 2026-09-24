import { CloudOff, RefreshCw, SatelliteDish } from 'lucide-react';

function Block({ className = '' }: { className?: string }) {
  return <div className={`ss-skeleton rounded-lg ${className}`} />;
}

/** Placeholder layout shown while a forecast loads. Mirrors the real dashboard so nothing jumps. */
export function DashboardSkeleton() {
  return (
    <div className="space-y-8" aria-busy="true" aria-label="Loading forecast">
      <div className="grid grid-cols-2 gap-6 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className={i === 0 ? 'col-span-2 sm:col-span-1' : ''}>
            <Block className="h-12 w-40" />
            <Block className="mt-3 h-3 w-16" />
            <Block className="mt-3 h-3 w-28" />
          </div>
        ))}
      </div>
      <div className="rounded-2xl border border-line bg-surface p-6">
        <Block className="h-4 w-72" />
        <Block className="mt-3 h-3 w-96 max-w-full" />
        <Block className="mt-6 h-72 w-full" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-line bg-surface p-6">
          <Block className="h-4 w-40" />
          <Block className="mt-6 h-52 w-full" />
        </div>
        <div className="rounded-2xl border border-line bg-surface p-6">
          <Block className="h-4 w-48" />
          <Block className="mt-6 h-52 w-full" />
        </div>
      </div>
    </div>
  );
}

export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <section className="flex h-full min-h-[320px] flex-col items-center justify-center rounded-2xl border border-dashed border-line-strong bg-surface/60 p-8 text-center">
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-mist text-muted">
        <SatelliteDish className="h-5 w-5" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-[15px] font-semibold text-ink">{title}</h2>
      <p className="mt-1.5 max-w-sm text-[14px] leading-relaxed text-muted">{message}</p>
    </section>
  );
}

export function ErrorState({ title, message, onRetry }: { title: string; message: string; onRetry?: () => void }) {
  return (
    <section className="flex h-full min-h-[320px] flex-col items-start justify-center rounded-2xl border border-sun-300/70 bg-surface p-6 sm:p-8">
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-sun-50 text-sun-700">
        <CloudOff className="h-5 w-5" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-[15px] font-semibold text-ink">{title}</h2>
      <p className="mt-1.5 max-w-md text-[14px] leading-relaxed text-muted">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="lift mt-5 inline-flex items-center gap-2 rounded-full border border-line-strong bg-surface px-4 py-2 text-[14px] font-medium text-ink hover:border-faint"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Retry
        </button>
      )}
    </section>
  );
}
