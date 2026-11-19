import { Clock } from 'lucide-react';
import { clsx } from 'clsx';

/** A 429 is a short wait, not a failure: neutral tone, announced once via role="status". */
export function RateLimitNotice({ message, className }: { message: string; className?: string }) {
  return (
    <div
      role="status"
      data-testid="rate-limit-notice"
      className={clsx(
        'flex items-start gap-2 rounded-lg border border-[var(--ff-border)] bg-[var(--ff-surface)] p-3',
        className,
      )}
    >
      <Clock className="mt-0.5 h-5 w-5 flex-shrink-0 text-[var(--ff-text-muted)]" aria-hidden="true" />
      <p className="text-sm text-[var(--ff-text)]">{message}</p>
    </div>
  );
}
