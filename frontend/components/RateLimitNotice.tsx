import { Clock } from 'lucide-react';
import { clsx } from 'clsx';

/**
 * A 429 is a short wait, not a failure: neutral tone, announced once via role="status".
 *
 * The status region is always mounted, empty until there is a message (W3C ARIA22 step 1): screen
 * readers such as NVDA and JAWS announce changes inside a live region they already know, not one
 * inserted together with its text. Render it unconditionally and pass `message={null}` when there
 * is no wait. The countdown stays on the button, outside this region, so it never re-announces.
 *
 * `className` (spacing) goes on the visible box, not the region, so the empty region takes no room;
 * `empty:!my-0` also drops a parent's `space-y-*` margin while it is empty (in block flow that margin
 * collapses through the empty box anyway; this keeps it at 0 in a flex or grid parent too).
 */
export function RateLimitNotice({ message, className }: { message: string | null; className?: string }) {
  return (
    <div role="status" aria-atomic="true" data-testid="rate-limit-region" className="empty:!my-0">
      {message ? (
        <div
          data-testid="rate-limit-notice"
          className={clsx(
            'flex items-start gap-2 rounded-lg border border-[var(--ff-border)] bg-[var(--ff-surface)] p-3',
            className,
          )}
        >
          <Clock className="mt-0.5 h-5 w-5 flex-shrink-0 text-[var(--ff-text-muted)]" aria-hidden="true" />
          <p className="text-sm text-[var(--ff-text)]">{message}</p>
        </div>
      ) : null}
    </div>
  );
}
