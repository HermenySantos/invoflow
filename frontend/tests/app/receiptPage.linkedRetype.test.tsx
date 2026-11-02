import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import { PRINTED_PAIR_LABEL, SERIES_MISMATCH_DETAIL } from '@/lib/reviewEdit';
import type { Document } from '@/lib/api';
import { getUseParamsMock } from '../navigationState';

const updateDocument = vi.fn();

vi.mock('@/lib/api', () => ({
  api: {
    getDocument: vi.fn(),
    getDocumentAuditTrail: vi.fn().mockResolvedValue({ entries: [], total: 0 }),
    updateDocument: (...args: unknown[]) => updateDocument(...args),
    deleteDocument: vi.fn(),
  },
}));

import { api } from '@/lib/api';
import ReceiptDetailPage from '@/app/receipts/[id]/page';

function receipt(overrides: Partial<Document> = {}): Document {
  return {
    id: 'doc-linked',
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
    ...overrides,
  };
}

function renderPage() {
  localStorage.setItem(
    DEMO_AUTH_KEY,
    JSON.stringify({ email: 'qa@example.com', id: 'ignored' }),
  );
  return render(
    <AuthProvider>
      <ReceiptDetailPage />
    </AuthProvider>,
  );
}

const LINKED = {
  status: 'needs_review' as const,
  document_type: 'FT',
  invoice_number: 'FT 2026/12',
  at_document_type: 'FT',
  at_invoice_number: 'FT 2026/12',
  linked_at_pair: { document_type: 'FT', invoice_number: 'FT 2026/12' },
};

describe('retype lock on a linked e-Fatura scan', () => {
  beforeEach(() => {
    updateDocument.mockReset();
    updateDocument.mockResolvedValue(receipt(LINKED));
    getUseParamsMock().mockReset();
    getUseParamsMock().mockReturnValue({ id: 'doc-linked' });
    vi.mocked(api.getDocument).mockResolvedValue(receipt(LINKED));
  });

  afterEach(() => {
    getUseParamsMock().mockReset();
    getUseParamsMock().mockImplementation(() => ({ id: 'doc-linked' }));
  });

  it.each([
    ['FS', 'FS 2026/12'],
    ['FS', '2026/12'],
    ['FR', 'FR 2026/12'],
  ])('refuses %s with %s and shows the PT-PT error', async (type, number) => {
    renderPage();
    await screen.findByRole('button', { name: 'Está correto' });
    fireEvent.click(screen.getByRole('button', { name: 'Editar dados' }));
    fireEvent.change(screen.getByLabelText('Tipo de documento'), { target: { value: type } });
    fireEvent.change(screen.getByLabelText('N.º da fatura'), { target: { value: number } });
    const save = screen.getByRole('button', { name: 'Guardar e confirmar' });
    expect(screen.getByText(SERIES_MISMATCH_DETAIL)).toBeInTheDocument();
    expect(screen.queryByLabelText(PRINTED_PAIR_LABEL)).not.toBeInTheDocument();
    expect(save).toBeDisabled();
    fireEvent.click(save);
    expect(updateDocument).not.toHaveBeenCalled();
  });

  it('saves a number edit that keeps the type', async () => {
    renderPage();
    await screen.findByRole('button', { name: 'Está correto' });
    fireEvent.click(screen.getByRole('button', { name: 'Editar dados' }));
    fireEvent.change(screen.getByLabelText('N.º da fatura'), { target: { value: 'FT 2026/13' } });
    const save = screen.getByRole('button', { name: 'Guardar e confirmar' });
    expect(screen.queryByText(SERIES_MISMATCH_DETAIL)).not.toBeInTheDocument();
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(updateDocument).toHaveBeenCalledTimes(1));
    expect(updateDocument.mock.calls[0][1]).toMatchObject({
      document_type: 'FT',
      invoice_number: 'FT 2026/13',
    });
  });
});
