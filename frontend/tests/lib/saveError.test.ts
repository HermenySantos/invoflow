import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  SAVE_CONFLICT_ERROR,
  SAVE_GENERIC_ERROR,
  SAVE_INVALID_ERROR,
  SAVE_UNAVAILABLE_ERROR,
  SAVE_NOT_FOUND_ERROR,
  SAVE_OFFLINE_ERROR,
  SAVE_SESSION_ERROR,
  SAVE_UNREACHABLE_ERROR,
  saveErrorMessage,
} from '@/lib/saveError';
import { rateLimitSaveStatus } from '@/lib/rateLimitCopy';

const EDIT_BUSY =
  'Está a decorrer uma importação do e-Fatura nesta conta. As alterações não foram ' +
  'guardadas; tente guardar novamente dentro de momentos.';
const DB_BUSY =
  'Outra operação nesta conta estava a decorrer ao mesmo tempo. Nada foi guardado; tente novamente dentro de momentos.';
const DUPLICATE = 'Já existe outro documento com o n.º FT A/1.';
const AMOUNT_MISMATCH = 'O valor líquido mais o IVA tem de ser igual ao total.';

/** Words of the English texts a proxy, framework or handler may put in the body. */
const ENGLISH_WORDS =
  /\b(conflict|invoice|already|exists|service|unavailable|error|invalid|request|data|failed|database|constraint|violation|entity|the)\b/i;

const STATUS_FALLBACK: Record<number, string> = {
  409: SAVE_CONFLICT_ERROR,
  422: SAVE_INVALID_ERROR,
  503: SAVE_UNAVAILABLE_ERROR,
};

/** backend/app/api/documents.py, schemas/document.py and core/db_errors.py, for PATCH /documents/{id}. */
const BACKEND_DETAILS: Record<number, string[]> = {
  409: ['Já existe outro documento com este NIF e n.º.', DUPLICATE, 'Já existe outro documento com o n.º 2026/12.'],
  422: [
    AMOUNT_MISMATCH,
    'Indique o tipo de documento antes de o marcar como pronto.',
    'O tipo de documento não pode ficar vazio.',
    'O n.º do documento não corresponde ao tipo indicado.',
  ],
  503: [
    EDIT_BUSY,
    DB_BUSY,
    'A operação demorou demasiado e foi interrompida. Nada foi guardado; tente novamente.',
  ],
};

const BROWSER_FETCH_FAILURES = [
  new TypeError('Failed to fetch'),
  new TypeError('Load failed'),
  new TypeError('NetworkError when attempting to fetch resource.'),
];

describe('saveErrorMessage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps the PT-PT 503 and 409 copy from the API unchanged', () => {
    expect(saveErrorMessage({ status: 503, message: EDIT_BUSY }, false)).toBe(EDIT_BUSY);
    expect(saveErrorMessage({ status: 503, message: DB_BUSY }, false)).toBe(DB_BUSY);
    expect(saveErrorMessage({ status: 409, message: DUPLICATE }, false)).toBe(DUPLICATE);
  });

  it('keeps the PT-PT 422 validation copy', () => {
    expect(saveErrorMessage({ status: 422, message: AMOUNT_MISMATCH }, false)).toBe(AMOUNT_MISMATCH);
  });

  it.each(BROWSER_FETCH_FAILURES)('maps a fetch failure while offline to the offline copy: %s', (err) => {
    expect(saveErrorMessage(err, true)).toBe(SAVE_OFFLINE_ERROR);
  });

  it.each(BROWSER_FETCH_FAILURES)('maps a fetch failure while online to the unreachable copy: %s', (err) => {
    expect(saveErrorMessage(err, false)).toBe(SAVE_UNREACHABLE_ERROR);
  });

  it('reads navigator.onLine when not told', () => {
    vi.stubGlobal('navigator', { onLine: false });
    expect(saveErrorMessage(new TypeError('Failed to fetch'))).toBe(SAVE_OFFLINE_ERROR);
    vi.stubGlobal('navigator', { onLine: true });
    expect(saveErrorMessage(new TypeError('Failed to fetch'))).toBe(SAVE_UNREACHABLE_ERROR);
  });

  it('never shows the text of a non-API error', () => {
    for (const err of [
      new Error('Something broke'),
      new DOMException('The user aborted a request.', 'AbortError'),
      'Failed to fetch',
      { message: 'Failed to fetch' },
      null,
      undefined,
    ]) {
      expect(saveErrorMessage(err, false)).toBe(SAVE_GENERIC_ERROR);
      expect(saveErrorMessage(err, true)).toBe(SAVE_OFFLINE_ERROR);
    }
  });

  it('replaces the English details the API can send for a save', () => {
    expect(saveErrorMessage({ status: 404, message: 'Document not found' }, false)).toBe(SAVE_NOT_FOUND_ERROR);
    expect(saveErrorMessage({ status: 401, message: 'Invalid or expired token' }, false)).toBe(SAVE_SESSION_ERROR);
    expect(saveErrorMessage({ status: 401, message: 'Failed to fetch authentication keys' }, false)).toBe(
      SAVE_SESSION_ERROR,
    );
    expect(saveErrorMessage({ status: 403, message: 'Forbidden' }, false)).toBe(SAVE_SESSION_ERROR);
    expect(saveErrorMessage({ status: 500, message: 'Failed to update document' }, false)).toBe(SAVE_GENERIC_ERROR);
    expect(saveErrorMessage({ status: 502, message: 'API Error: Bad Gateway' }, false)).toBe(SAVE_GENERIC_ERROR);
    expect(saveErrorMessage({ status: 409, message: 'Database constraint violation' }, false)).toBe(
      SAVE_CONFLICT_ERROR,
    );
    expect(saveErrorMessage({ status: 422, message: 'Invalid request data' }, false)).toBe(SAVE_INVALID_ERROR);
    expect(saveErrorMessage({ status: 503, message: 'API Error: Service Unavailable' }, false)).toBe(
      SAVE_UNAVAILABLE_ERROR,
    );
    expect(saveErrorMessage({ status: 503, message: '  ' }, false)).toBe(SAVE_UNAVAILABLE_ERROR);
  });

  it('replaces an injected English 409 with the PT-PT conflict copy', () => {
    const shown = saveErrorMessage({ status: 409, message: 'Conflict: invoice already exists' }, false);
    expect(shown).toBe(SAVE_CONFLICT_ERROR);
    expect(shown).not.toMatch(ENGLISH_WORDS);
  });

  it('replaces an injected English 503 with the PT-PT unavailable copy', () => {
    const shown = saveErrorMessage({ status: 503, message: 'Service Unavailable' }, false);
    expect(shown).toBe(SAVE_UNAVAILABLE_ERROR);
    expect(shown).not.toMatch(ENGLISH_WORDS);
  });

  it.each([409, 422, 503])('passes no unknown %i detail through, PT-PT-looking or not', (status) => {
    for (const message of [
      'Conflict: invoice already exists',
      'Service Unavailable',
      'Unprocessable Entity',
      'value is not a valid decimal',
      'Erro interno qualquer',
      'Já existe outro documento com o n.º ',
    ]) {
      const shown = saveErrorMessage({ status, message }, false);
      expect(shown).toBe(STATUS_FALLBACK[status]);
      expect(shown).not.toMatch(ENGLISH_WORDS);
    }
  });

  it('keeps every PT-PT detail the save endpoint sends', () => {
    for (const [status, messages] of Object.entries(BACKEND_DETAILS)) {
      for (const message of messages) {
        expect(saveErrorMessage({ status: Number(status), message: `  ${message} ` }, false)).toBe(message);
      }
    }
  });

  it.each([
    'Já existe outro documento com o n.º FT 2026/12.',
    'Já existe outro documento com o n.º NC. 2026/5.',
    'Já existe outro documento com o n.º N C A/5.',
    'Já existe outro documento com o n.º NC1 2026.',
    'Já existe outro documento com o n.º FR-2026/0001.',
  ])('keeps a 409 duplicate detail that names a real document number: %s', (message) => {
    expect(saveErrorMessage({ status: 409, message }, false)).toBe(message);
  });

  it.each([
    `${DUPLICATE} Please try again.`,
    `${DUPLICATE} Conflict.`,
    `${DUPLICATE} OK.`,
    'Já existe outro documento com o n.º FT K/1..',
    'Já existe outro documento com o n.º FT K/1...',
    'Já existe outro documento com o n.º FT A/1. Please retry.',
    'Já existe outro documento com o n.º FT A/1 already exists.',
    'Já existe outro documento com o n.º FT A/1 in use.',
    'Já existe outro documento com o n.º FT A/1 (conflict).',
    'Já existe outro documento com o n.º FT A/1 - see logs.',
    'Já existe outro documento com o n.º FT A/1.\nDuplicate key value violates unique constraint.',
    'Já existe outro documento com o n.º FT A/1: "Conflict".',
    'Já existe outro documento com o n.º invoice already exists.',
    `Já existe outro documento com o n.º ${'1'.repeat(101)}.`,
    'Já existe outro documento com este NIF e n.º. Conflict.',
    `${EDIT_BUSY} Service Unavailable.`,
    `${AMOUNT_MISMATCH} Invalid request data.`,
  ])('replaces a PT-PT detail with text appended by the fixed copy: %s', (message) => {
    const status = message.startsWith('Já existe') ? 409 : message.startsWith('O valor') ? 422 : 503;
    const shown = saveErrorMessage({ status, message }, false);
    expect(shown).toBe(STATUS_FALLBACK[status]);
    expect(shown).not.toMatch(ENGLISH_WORDS);
  });

  it('does not let a known detail through under another status', () => {
    expect(saveErrorMessage({ status: 422, message: EDIT_BUSY }, false)).toBe(SAVE_INVALID_ERROR);
    expect(saveErrorMessage({ status: 503, message: DUPLICATE }, false)).toBe(SAVE_UNAVAILABLE_ERROR);
    expect(saveErrorMessage({ status: 500, message: AMOUNT_MISMATCH }, false)).toBe(SAVE_GENERIC_ERROR);
  });

  it('writes its fallback copy in PT-PT', () => {
    for (const copy of [SAVE_CONFLICT_ERROR, SAVE_INVALID_ERROR, SAVE_UNAVAILABLE_ERROR]) {
      expect(copy).not.toMatch(ENGLISH_WORDS);
    }
  });

  it('uses the API answer over the offline flag: the server did reply', () => {
    expect(saveErrorMessage({ status: 503, message: EDIT_BUSY }, true)).toBe(EDIT_BUSY);
  });

  it('names the wait on a 429 and says the changes were not saved, never SAVE_GENERIC_ERROR', () => {
    const detail = 'Demasiados pedidos. Aguarde 17 s e tente novamente.';
    const withHeader = saveErrorMessage({ status: 429, message: detail, retryAfter: 42 }, false);
    expect(withHeader).toBe(rateLimitSaveStatus(42));
    expect(withHeader).not.toBe(SAVE_GENERIC_ERROR);
    expect(withHeader).not.toMatch(/Tente (novamente|outra vez)/i);
    expect(saveErrorMessage({ status: 429, message: detail }, false)).toBe(rateLimitSaveStatus(17));
  });
});
