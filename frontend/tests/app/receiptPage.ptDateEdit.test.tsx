import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axe from 'axe-core';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import type { Document } from '@/lib/api';
import { PT_DATE_INVALID } from '@/lib/ptDate';
import ReceiptDetailPage from '@/app/receipts/[id]/page';
import { getUseParamsMock } from '../navigationState';

function receipt(): Document {
  return {
    id: 'doc-edit-date',
    user_id: 'user-1',
    status: 'ready',
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

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: () => Promise.resolve(body),
  };
}

function stubFetch() {
  const fetchMock = vi.fn((url: string, _init?: RequestInit) => {
    if (url.includes('/audit')) return Promise.resolve(jsonResponse({ entries: [], total: 0 }));
    return Promise.resolve(jsonResponse(receipt()));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function patchBodies(fetchMock: ReturnType<typeof stubFetch>) {
  return fetchMock.mock.calls
    .filter(([, init]) => init?.method === 'PATCH')
    .map(([, init]) => JSON.parse(String(init?.body)));
}

async function openEdit() {
  const view = render(
    <AuthProvider>
      <ReceiptDetailPage />
    </AuthProvider>,
  );
  fireEvent.click(await screen.findByRole('button', { name: 'Editar dados' }));
  return { ...view, input: screen.getByLabelText('Data do documento') };
}

describe('receipt edit form date reads dd/mm/aaaa', () => {
  beforeEach(() => {
    getUseParamsMock().mockReturnValue({ id: 'doc-edit-date' });
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ email: 'qa@example.com', id: 'ignored' }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.removeItem(DEMO_AUTH_KEY);
  });

  it('shows the stored date as dd/mm/aaaa in a text field, never mm/dd/yyyy', async () => {
    stubFetch();
    const { container, input } = await openEdit();
    expect(input).toHaveAttribute('type', 'text');
    expect(input).toHaveAttribute('placeholder', 'dd/mm/aaaa');
    expect(input).toHaveAttribute('inputmode', 'numeric');
    expect(input).toHaveValue('15/03/2026');
    expect(container.querySelector('input[type="date"]')).toBeNull();
    expect(container.innerHTML).not.toMatch(/mm\/dd\/yyyy/i);
    const result = await axe.run(container, { runOnly: { type: 'rule', values: ['label'] } });
    expect(result.violations).toEqual([]);
  });

  it('saves a typed dd/mm/aaaa date as ISO', async () => {
    const fetchMock = stubFetch();
    const { input } = await openEdit();
    fireEvent.change(input, { target: { value: '01/02/2026' } });
    fireEvent.blur(input);
    fireEvent.click(screen.getByRole('button', { name: /Guardar/ }));
    await waitFor(() => expect(patchBodies(fetchMock)).toHaveLength(1));
    expect(patchBodies(fetchMock)[0].document_date).toBe('2026-02-01');
  });

  it('does not save 32/13/2026', async () => {
    const fetchMock = stubFetch();
    const { input } = await openEdit();
    fireEvent.change(input, { target: { value: '32/13/2026' } });
    fireEvent.blur(input);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription(PT_DATE_INVALID);
    fireEvent.click(screen.getByRole('button', { name: /Guardar/ }));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(patchBodies(fetchMock)).toHaveLength(0);
  });
});
