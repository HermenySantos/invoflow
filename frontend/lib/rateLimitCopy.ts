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

/**
 * Accessible name of a button during a 429 wait (Conversion Lead, COPY-TOKENS-v1 §4a). Fixed, with no
 * seconds: the button keeps focus while it waits, and a focused control whose name ticks is re-read
 * every second (UI Lead F-2). The visible countdown (rateLimitButton) is aria-hidden.
 */
export const RATE_LIMIT_BUTTON_LABEL = 'Tentar de novo (aguarde um momento)';

/** Visible only (aria-hidden): the name is RATE_LIMIT_BUTTON_LABEL. */
export function rateLimitButton(seconds: number): string {
  return `Tentar de novo em ${seconds} s`;
}
