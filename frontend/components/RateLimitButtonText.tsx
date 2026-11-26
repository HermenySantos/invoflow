import { RATE_LIMIT_BUTTON_TEXT, RATE_LIMIT_BUTTON_WAIT_HINT, rateLimitButtonTick } from '@/lib/rateLimitCopy';

/**
 * Content of a button during a 429 wait. Sighted users read "Tentar de novo em N s"; the accessible
 * name is the fixed RATE_LIMIT_BUTTON_LABEL, "Tentar de novo (aguarde um momento)", which contains the
 * visible label (WCAG 2.5.3) and doesn't tick (UI Lead F-2, R2-1). Never pair it with an aria-label.
 * One wrapping span keeps the three parts a single flex item, so the spaces survive in `gap-*` buttons.
 */
export function RateLimitButtonText({ seconds }: { seconds: number }) {
  return (
    <span>
      {RATE_LIMIT_BUTTON_TEXT}
      <span aria-hidden="true">{rateLimitButtonTick(seconds)}</span>
      <span className="sr-only">{RATE_LIMIT_BUTTON_WAIT_HINT}</span>
    </span>
  );
}
