import { SERIES_MISMATCH_DETAIL } from './reviewEdit';

export const SAVE_OFFLINE_ERROR =
  'Sem ligação. As alterações não foram guardadas. Tente de novo quando estiver online.';
export const SAVE_UNREACHABLE_ERROR =
  'Não foi possível contactar o servidor. As alterações não foram guardadas. Tente de novo dentro de momentos.';
export const SAVE_GENERIC_ERROR = 'Não foi possível guardar. Tente novamente.';
export const SAVE_NOT_FOUND_ERROR = 'Este recibo já não existe. Volte à lista de recibos.';
export const SAVE_SESSION_ERROR = 'A sessão terminou. Inicie sessão de novo e tente outra vez.';

export const SAVE_CONFLICT_ERROR =
  'As alterações entram em conflito com outro documento e não foram guardadas. Reveja o NIF e o n.º e tente novamente.';
export const SAVE_INVALID_ERROR = 'Há dados do recibo que não são válidos. Reveja os campos e tente novamente.';
export const SAVE_UNAVAILABLE_ERROR =
  'O serviço está temporariamente indisponível. As alterações não foram guardadas; tente novamente dentro de momentos.';

const STATUS_FALLBACKS: Record<number, string> = {
  409: SAVE_CONFLICT_ERROR,
  422: SAVE_INVALID_ERROR,
  503: SAVE_UNAVAILABLE_ERROR,
};

/** The PT-PT details PATCH /documents/{id} sends, per status. Must match the backend constants word for word. */
const KNOWN_PT_PT_DETAILS: Record<number, ReadonlySet<string>> = {
  409: new Set(['Já existe outro documento com este NIF e n.º.']),
  422: new Set([
    'O valor líquido mais o IVA tem de ser igual ao total.',
    'Indique o tipo de documento antes de o marcar como pronto.',
    'O tipo de documento não pode ficar vazio.',
    SERIES_MISMATCH_DETAIL,
  ]),
  503: new Set([
    'Está a decorrer uma importação do e-Fatura nesta conta. As alterações não foram guardadas; tente guardar novamente dentro de momentos.',
    'Outra operação nesta conta estava a decorrer ao mesmo tempo. Nada foi guardado; tente novamente dentro de momentos.',
    'A operação demorou demasiado e foi interrompida. Nada foi guardado; tente novamente.',
  ]),
};

/** The 409 duplicate detail that names the other document's number. */
const DUPLICATE_NUMBER_DETAIL = /^Já existe outro documento com o n\.º \S.*\.$/;

function isKnownPtPtDetail(status: number, message: string): boolean {
  if (KNOWN_PT_PT_DETAILS[status]?.has(message)) return true;
  return status === 409 && DUPLICATE_NUMBER_DETAIL.test(message);
}

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
    if (isKnownPtPtDetail(err.status, message)) return message;
    if (STATUS_FALLBACKS[err.status]) return STATUS_FALLBACKS[err.status];
    if (err.status === 404) return SAVE_NOT_FOUND_ERROR;
    if (err.status === 401 || err.status === 403) return SAVE_SESSION_ERROR;
    return SAVE_GENERIC_ERROR;
  }
  if (offline) return SAVE_OFFLINE_ERROR;
  if (err instanceof TypeError) return SAVE_UNREACHABLE_ERROR;
  return SAVE_GENERIC_ERROR;
}
