export const SAVE_OFFLINE_ERROR =
  'Sem ligação. As alterações não foram guardadas. Tente de novo quando estiver online.';
export const SAVE_UNREACHABLE_ERROR =
  'Não foi possível contactar o servidor. As alterações não foram guardadas. Tente de novo dentro de momentos.';
export const SAVE_GENERIC_ERROR = 'Não foi possível guardar. Tente novamente.';
export const SAVE_NOT_FOUND_ERROR = 'Este recibo já não existe. Volte à lista de recibos.';
export const SAVE_SESSION_ERROR = 'A sessão terminou. Inicie sessão de novo e tente outra vez.';

/** Statuses whose `detail` the backend writes in PT-PT for a save (lock clash, duplicate number, validation). */
const PT_PT_DETAIL_STATUSES = new Set([409, 422, 503]);

/** English messages the backend's global handlers send under those same statuses. */
const ENGLISH_HANDLER_MESSAGES = new Set(['Database constraint violation', 'Invalid request data']);

interface ApiFailure {
  status: number;
  message: string;
}

function isApiFailure(err: unknown): err is ApiFailure {
  return (
    typeof err === 'object' &&
    err !== null &&
    typeof (err as { status?: unknown }).status === 'number' &&
    typeof (err as { message?: unknown }).message === 'string'
  );
}

function browserOffline(): boolean {
  return typeof navigator !== 'undefined' && navigator.onLine === false;
}

/**
 * PT-PT copy for a failed receipt save. fetch() rejects with a TypeError whose text depends on the
 * browser ('Failed to fetch', 'Load failed', 'NetworkError when attempting to fetch resource.'),
 * so no error's own text is shown unless it is an API detail known to be PT-PT.
 */
export function saveErrorMessage(err: unknown, offline: boolean = browserOffline()): string {
  if (isApiFailure(err)) {
    const message = err.message.trim();
    if (
      PT_PT_DETAIL_STATUSES.has(err.status) &&
      message &&
      !message.startsWith('API Error') &&
      !ENGLISH_HANDLER_MESSAGES.has(message)
    ) {
      return message;
    }
    if (err.status === 404) return SAVE_NOT_FOUND_ERROR;
    if (err.status === 401 || err.status === 403) return SAVE_SESSION_ERROR;
    return SAVE_GENERIC_ERROR;
  }
  if (offline) return SAVE_OFFLINE_ERROR;
  if (err instanceof TypeError) return SAVE_UNREACHABLE_ERROR;
  return SAVE_GENERIC_ERROR;
}
