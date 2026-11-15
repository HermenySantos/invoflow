import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  SAVE_GENERIC_ERROR,
  SAVE_NOT_FOUND_ERROR,
  SAVE_OFFLINE_ERROR,
  SAVE_SESSION_ERROR,
  SAVE_UNREACHABLE_ERROR,
  saveErrorMessage,
} from '@/lib/saveError';

const EDIT_BUSY =
  'Está a decorrer uma importação do e-Fatura nesta conta. As alterações não foram ' +
  'guardadas; tente guardar novamente dentro de momentos.';
const DB_BUSY =
  'Outra operação nesta conta estava a decorrer ao mesmo tempo. Nada foi guardado; tente novamente dentro de momentos.';
const DUPLICATE = 'Já existe outro documento com o n.º FT A/1.';
const AMOUNT_MISMATCH = 'O valor líquido mais o IVA tem de ser igual ao total.';

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
      SAVE_GENERIC_ERROR,
    );
    expect(saveErrorMessage({ status: 422, message: 'Invalid request data' }, false)).toBe(SAVE_GENERIC_ERROR);
    expect(saveErrorMessage({ status: 503, message: 'API Error: Service Unavailable' }, false)).toBe(
      SAVE_GENERIC_ERROR,
    );
    expect(saveErrorMessage({ status: 503, message: '  ' }, false)).toBe(SAVE_GENERIC_ERROR);
  });

  it('uses the API answer over the offline flag: the server did reply', () => {
    expect(saveErrorMessage({ status: 503, message: EDIT_BUSY }, true)).toBe(EDIT_BUSY);
  });
});
