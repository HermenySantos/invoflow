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

export function rateLimitButton(seconds: number): string {
  return `Tentar de novo em ${seconds} s`;
}
