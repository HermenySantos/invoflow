/** PT-PT copy for a 429 (Conversion Lead, COPY-TOKENS-v1 §4). Every line names the wait: never a bare "Tente novamente". */

export const RATE_LIMIT_SAVE_ADDON = 'As alterações não foram guardadas.';
export const RATE_LIMIT_UPLOAD_ADDON = 'O ficheiro continua selecionado.';

export function rateLimitStatus(seconds: number): string {
  return `Aguarde um momento. Pode tentar de novo dentro de ${seconds} s.`;
}

export function rateLimitSaveStatus(seconds: number): string {
  return `${RATE_LIMIT_SAVE_ADDON} ${rateLimitStatus(seconds)}`;
}

export function rateLimitUploadStatus(seconds: number): string {
  return `${RATE_LIMIT_UPLOAD_ADDON} ${rateLimitStatus(seconds)}`;
}

/** Visible start of a waiting button's text; also the start of its accessible name (WCAG 2.5.3). */
export const RATE_LIMIT_BUTTON_TEXT = 'Tentar de novo';
/** Screen-reader-only end of the name (sr-only). Replaces the ticking seconds for assistive tech. */
export const RATE_LIMIT_BUTTON_WAIT_HINT = ' (aguarde um momento)';

/**
 * Accessible name of a button during a 429 wait (Conversion Lead, COPY-TOKENS-v1 §4a). Fixed, with no
 * seconds: the button keeps focus while it waits, and a focused control whose name ticks is re-read
 * every second (UI Lead F-2). It comes from content, not aria-label, so it contains the visible label
 * (UI Lead R2-1, WCAG 2.5.3): RATE_LIMIT_BUTTON_TEXT + sr-only RATE_LIMIT_BUTTON_WAIT_HINT, with the
 * seconds aria-hidden. Rendered by components/RateLimitButtonText.tsx.
 */
export const RATE_LIMIT_BUTTON_LABEL = `${RATE_LIMIT_BUTTON_TEXT}${RATE_LIMIT_BUTTON_WAIT_HINT}`;

/** Visible-only (aria-hidden) countdown that follows RATE_LIMIT_BUTTON_TEXT. */
export function rateLimitButtonTick(seconds: number): string {
  return ` em ${seconds} s`;
}

/** What a sighted user reads on the waiting button. */
export function rateLimitButton(seconds: number): string {
  return `${RATE_LIMIT_BUTTON_TEXT}${rateLimitButtonTick(seconds)}`;
}
