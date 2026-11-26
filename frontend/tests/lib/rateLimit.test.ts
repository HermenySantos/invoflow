import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { api } from '@/lib/api';
import { RATE_LIMIT_FALLBACK_SECONDS, parseRetryAfter, rateLimitWait, useRetryCountdown } from '@/lib/rateLimit';
import { rateLimitButton, rateLimitSaveStatus, rateLimitStatus, rateLimitUploadStatus } from '@/lib/rateLimitCopy';

const BARE_RETRY = /Tente (novamente|outra vez)/i;
const BACKEND_DETAIL = (s: number) => `Demasiados pedidos. Aguarde ${s} s e tente novamente.`;

function response(status: number, body: unknown, headers: Record<string, string> = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 429 ? 'Too Many Requests' : 'OK',
    headers: new Headers({ 'content-type': 'application/json', ...headers }),
    json: () => Promise.resolve(body),
    blob: () => Promise.resolve(new Blob(['zip'])),
  };
}

const RATE_LIMITED_BODY = (s: number) => ({ detail: BACKEND_DETAIL(s), error: { code: 'RATE_LIMITED' } });

describe('rateLimitWait', () => {
  it('reads Retry-After first', () => {
    expect(rateLimitWait({ status: 429, message: BACKEND_DETAIL(10), retryAfter: 42 })).toBe(42);
  });

  it('falls back to "Aguarde N s" in the detail', () => {
    expect(rateLimitWait({ status: 429, message: BACKEND_DETAIL(17), retryAfter: null })).toBe(17);
  });

  it('uses the longest window when a 429 says nothing about the wait', () => {
    expect(rateLimitWait({ status: 429, message: 'Too Many Requests', retryAfter: null })).toBe(
      RATE_LIMIT_FALLBACK_SECONDS,
    );
  });

  it('is null for anything that is not a 429, even a 503 with Retry-After', () => {
    expect(rateLimitWait({ status: 503, message: 'x', retryAfter: 10 })).toBeNull();
    expect(rateLimitWait(new TypeError('Failed to fetch'))).toBeNull();
    expect(rateLimitWait(null)).toBeNull();
  });
});

describe('parseRetryAfter', () => {
  it('accepts delay-seconds and an HTTP-date', () => {
    expect(parseRetryAfter('42')).toBe(42);
    const now = Date.parse('2026-11-19T10:00:00Z');
    expect(parseRetryAfter('Thu, 19 Nov 2026 10:00:30 GMT', now)).toBe(30);
  });

  it('ignores missing, zero and garbage values', () => {
    expect(parseRetryAfter(null)).toBeNull();
    expect(parseRetryAfter('0')).toBeNull();
    expect(parseRetryAfter('soon')).toBeNull();
  });
});

describe('429 copy', () => {
  it.each([
    ['status', rateLimitStatus(42), 'Aguarde um momento. Pode tentar de novo dentro de 42 s.'],
    ['save', rateLimitSaveStatus(42), 'As alterações não foram guardadas. Aguarde um momento. Pode tentar de novo dentro de 42 s.'],
    ['upload', rateLimitUploadStatus(42), 'O ficheiro continua selecionado. Aguarde um momento. Pode tentar de novo dentro de 42 s.'],
    ['button', rateLimitButton(42), 'Tentar de novo em 42 s'],
  ])('%s line names the wait and never says a bare "Tente novamente"', (_name, text, expected) => {
    expect(text).toBe(expected);
    expect(text).toContain('42 s');
    expect(text).not.toMatch(BARE_RETRY);
  });
});

describe('useRetryCountdown', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('ticks once a second, keeps the message fixed, and clears at 0', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useRetryCountdown());
    act(() => result.current.start(3, rateLimitStatus(3)));
    expect(result.current.seconds).toBe(3);
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.seconds).toBe(2);
    expect(result.current.message).toBe(rateLimitStatus(3));
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.seconds).toBe(1);
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.seconds).toBeNull();
    expect(result.current.message).toBeNull();
  });

  it('clear() ends the wait early and stops the ticking', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useRetryCountdown());
    act(() => result.current.start(5, rateLimitStatus(5)));
    act(() => result.current.clear());
    expect(result.current.seconds).toBeNull();
    expect(result.current.message).toBeNull();
    act(() => vi.advanceTimersByTime(3000));
    expect(result.current.seconds).toBeNull();
  });
});

describe('API client failures carry {status, message, retryAfter}', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('downloadExport throws the 429 with Retry-After instead of a bare Error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(429, RATE_LIMITED_BODY(42), { 'Retry-After': '42' })));
    const err = await api.downloadExport({ period_type: 'month', year: 2026, month: 3 }).catch((e) => e);
    expect(err).not.toBeInstanceOf(Error);
    expect(err).toEqual({ status: 429, message: BACKEND_DETAIL(42), retryAfter: 42 });
    expect(rateLimitWait(err)).toBe(42);
  });

  it('downloadExport keeps the status of other failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(500, 'not json')));
    await expect(api.downloadExport()).rejects.toMatchObject({ status: 500, message: 'Export failed', retryAfter: null });
  });

  it('uploadFile throws the 429 from the upload-url step', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(429, RATE_LIMITED_BODY(20), { 'Retry-After': '20' })));
    const file = new File(['x'], 'recibo.jpg', { type: 'image/jpeg' });
    await expect(api.uploadFile(file)).rejects.toMatchObject({ status: 429, retryAfter: 20 });
  });

  it('uploadFile throws the 429 from the file PUT step', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(200, { upload_url: '/api/files/k', storage_key: 'k', expires_in: 60 }))
      .mockResolvedValueOnce(response(429, RATE_LIMITED_BODY(9), { 'Retry-After': '9' }));
    vi.stubGlobal('fetch', fetchMock);
    const file = new File(['x'], 'recibo.jpg', { type: 'image/jpeg' });
    const err = await api.uploadFile(file).catch((e) => e);
    expect(err).toEqual({ status: 429, message: BACKEND_DETAIL(9), retryAfter: 9 });
  });

  it('request() adds retryAfter to its errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(429, RATE_LIMITED_BODY(5), { 'Retry-After': '5' })));
    await expect(api.updateDocument('d', { vendor_name: 'x' })).rejects.toEqual({
      status: 429,
      message: BACKEND_DETAIL(5),
      retryAfter: 5,
    });
  });
});
