import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import type { Document } from '@/lib/api';
import {
  SAVE_CONFLICT_ERROR,
  SAVE_GENERIC_ERROR,
  SAVE_INVALID_ERROR,
  SAVE_UNAVAILABLE_ERROR,
} from '@/lib/saveError';
import ReceiptDetailPage from '@/app/receipts/[id]/page';
import { getUseParamsMock } from '../navigationState';
import { expectEmptyRegion, expectRegionSays, getRateLimitRegion } from '../rateLimitRegion';
import { RATE_LIMIT_BUTTON_LABEL } from '@/lib/rateLimitCopy';
import { expectAvailable, expectCountingDown, expectHeld } from '../softDisabled';

const ENGLISH_WORDS =
  /\b(conflict|invoice|already|exists|service|unavailable|error|invalid|request|data|failed|database|constraint|violation|entity|the)\b/i;

function receipt(): Document {
  return {
    id: 'doc-copy',
    user_id: 'user-1',
    status: 'needs_review',
    storage_key: 'user/recibo.jpg',
    original_filename: 'recibo.jpg',
    mime_type: 'image/jpeg',
    file_size: 1200,
    vendor_name: 'Oficina do Bairro',
    vendor_nif: '123456002',
    invoice_number: 'FT A/1',
    document_type: 'FT',
    suggested_type: null,
    suggested_invoice_number: null,
    at_document_type: null,
    at_invoice_number: null,
    document_date: '2026-03-15',
    net_amount: '10.00',
    vat_amount: '2.30',
    gross_amount: '12.30',
    vat_rate: '23.00',
    ocr_confidence: '90.00',
    field_confidence: null,
    validation_warnings: [],
    review_notes: null,
    expense_category: 'utilities',
    irs_sector: null,
    deductible_pct: 100,
    deductible_pct_override: null,
    period_tag: '2026-03',
    quarter_tag: '2026-Q1',
    file_url: null,
    thumbnail_url: null,
    created_at: '2026-03-15T12:00:00Z',
    updated_at: '2026-03-15T12:00:00Z',
  };
}

function jsonResponse(status: number, statusText: string, body: unknown, headers: Record<string, string> = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    headers: new Headers({ 'content-type': 'application/json', ...headers }),
    json: () => Promise.resolve(body),
  };
}

/** Real api.ts over a stubbed fetch: the PATCH answers with the given status and body. */
function stubFetch(saveStatus: number, saveStatusText: string, saveBody: unknown, saveHeaders: Record<string, string> = {}) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === 'PATCH') return Promise.resolve(jsonResponse(saveStatus, saveStatusText, saveBody, saveHeaders));
    if (url.includes('/audit')) return Promise.resolve(jsonResponse(200, 'OK', { entries: [], total: 0 }));
    return Promise.resolve(jsonResponse(200, 'OK', receipt()));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function saveAndReadAlert() {
  localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ email: 'qa@example.com', id: 'ignored' }));
  render(
    <AuthProvider>
      <ReceiptDetailPage />
    </AuthProvider>,
  );
  fireEvent.click(await screen.findByRole('button', { name: 'Está correto' }));
  return screen.findByRole('alert');
}

describe('receipt page save error copy from the API', () => {
  beforeEach(() => {
    getUseParamsMock().mockReturnValue({ id: 'doc-copy' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.removeItem(DEMO_AUTH_KEY);
  });

  it.each([
    [409, 'Conflict', { detail: 'Conflict: invoice already exists' }, SAVE_CONFLICT_ERROR],
    [409, 'Conflict', { error: { code: 'CONFLICT', message: 'Conflict: invoice already exists' } }, SAVE_CONFLICT_ERROR],
    [503, 'Service Unavailable', { detail: 'Service Unavailable' }, SAVE_UNAVAILABLE_ERROR],
    [503, 'Service Unavailable', { message: 'Service Unavailable' }, SAVE_UNAVAILABLE_ERROR],
    [503, 'Service Unavailable', 'not json', SAVE_UNAVAILABLE_ERROR],
    [422, 'Unprocessable Entity', { error: { code: 'VALIDATION_ERROR', message: 'Invalid request data' } }, SAVE_INVALID_ERROR],
  ])('shows PT-PT copy, never English, for a %i %s with body %j', async (status, statusText, body, expected) => {
    const fetchMock = stubFetch(status, statusText, body);
    const alert = await saveAndReadAlert();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/documents/doc-copy'), expect.objectContaining({ method: 'PATCH' }));
    expect(alert).toHaveTextContent(expected);
    expect(alert.textContent).not.toMatch(ENGLISH_WORDS);
  });

  it('the edit form save button keeps focus while saving and through a 429 wait (W-14)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let answer!: (r: unknown) => void;
      const fetchMock = vi.fn((url: string, init?: RequestInit) => {
        if (init?.method === 'PATCH') return new Promise((r) => (answer = r));
        if (url.includes('/audit')) return Promise.resolve(jsonResponse(200, 'OK', { entries: [], total: 0 }));
        return Promise.resolve(jsonResponse(200, 'OK', receipt()));
      });
      vi.stubGlobal('fetch', fetchMock);
      localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ email: 'qa@example.com', id: 'ignored' }));
      render(
        <AuthProvider>
          <ReceiptDetailPage />
        </AuthProvider>,
      );
      fireEvent.click(await screen.findByRole('button', { name: 'Editar dados' }));
      const save = screen.getByRole('button', { name: 'Guardar e confirmar' });
      const patches = () => fetchMock.mock.calls.filter(([, init]) => init?.method === 'PATCH').length;

      // Focus first, then the state changes (W-15).
      save.focus();
      fireEvent.click(save);
      await screen.findByText('A guardar...');
      expectHeld(save);
      fireEvent.click(save);
      expect(patches()).toBe(1);

      await act(async () => {
        answer(
          jsonResponse(
            429,
            'Too Many Requests',
            { detail: 'Demasiados pedidos. Aguarde 30 s e tente novamente.', error: { code: 'RATE_LIMITED' } },
            { 'Retry-After': '2' },
          ),
        );
      });
      const waiting = await screen.findByRole('button', { name: RATE_LIMIT_BUTTON_LABEL });
      expect(waiting).toBe(save);
      expectCountingDown(save, 2);
      fireEvent.click(save);
      expect(patches()).toBe(1);

      act(() => vi.advanceTimersByTime(1000));
      expectCountingDown(save, 1);
      act(() => vi.advanceTimersByTime(1000));
      expectAvailable(screen.getByRole('button', { name: 'Guardar e confirmar' }));
      expect(document.activeElement).toBe(save);
    } finally {
      vi.useRealTimers();
    }
  });

  it('on a 429 shows the save wait as a status, never SAVE_GENERIC_ERROR, and counts down on the button', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      stubFetch(
        429,
        'Too Many Requests',
        { detail: 'Demasiados pedidos. Aguarde 30 s e tente novamente.', error: { code: 'RATE_LIMITED' } },
        { 'Retry-After': '2' },
      );
      localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ email: 'qa@example.com', id: 'ignored' }));
      render(
        <AuthProvider>
          <ReceiptDetailPage />
        </AuthProvider>,
      );
      const saveButton = await screen.findByRole('button', { name: 'Está correto' });
      // ARIA22 step 1: the status region is already there, empty, before any 429.
      const regionBefore = getRateLimitRegion();
      expectEmptyRegion(regionBefore);
      saveButton.focus();
      fireEvent.click(saveButton);

      const notice = await screen.findByTestId('rate-limit-notice');
      const region = getRateLimitRegion();
      expect(region).toBe(regionBefore);
      expect(region).toContainElement(notice);
      expectRegionSays(region, 'As alterações não foram guardadas.');
      expect(notice).toHaveTextContent(
        'As alterações não foram guardadas. Aguarde um momento. Pode tentar de novo dentro de 2 s.',
      );
      expect(notice.textContent).not.toMatch(/Tente (novamente|outra vez)/i);
      expect(screen.queryByText(SAVE_GENERIC_ERROR)).not.toBeInTheDocument();
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();

      const button = screen.getByRole('button', { name: RATE_LIMIT_BUTTON_LABEL });
      expect(button).toBe(saveButton);
      expectCountingDown(button, 2);
      act(() => vi.advanceTimersByTime(1000));
      expectCountingDown(button, 1);
      act(() => vi.advanceTimersByTime(1000));
      expectAvailable(screen.getByRole('button', { name: 'Está correto' }));
      expect(document.activeElement).toBe(saveButton);
      expect(getRateLimitRegion()).toBe(regionBefore);
      expectEmptyRegion(regionBefore);
    } finally {
      vi.useRealTimers();
    }
  });

  it('still shows the PT-PT duplicate detail the backend writes', async () => {
    stubFetch(409, 'Conflict', { detail: 'Já existe outro documento com o n.º FT A/1.' });
    const alert = await saveAndReadAlert();
    expect(alert).toHaveTextContent('Já existe outro documento com o n.º FT A/1.');
  });
});
