import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import type { Document } from '@/lib/api';

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
    id: 'doc-v6',
    user_id: 'user-1',
    status: 'needs_review',
    storage_key: 'user/nota.png',
    original_filename: 'nota.png',
    mime_type: 'image/png',
    file_size: 1200,
    vendor_name: 'Padaria Exemplo Lda',
    vendor_nif: '123456002',
    invoice_number: null,
    document_type: 'unclassified',
    suggested_type: 'FT',
    suggested_invoice_number: 'FT A/12',
    at_document_type: null,
    document_date: '2026-03-31',
    net_amount: '8.13',
    vat_amount: '1.87',
    gross_amount: '10.00',
    vat_rate: '23.00',
    ocr_confidence: '80.00',
    field_confidence: null,
    validation_warnings: [],
    review_notes: null,
    expense_category: 'food',
    irs_sector: null,
    deductible_pct: 100,
    deductible_pct_override: null,
    period_tag: '2026-03',
    quarter_tag: '2026-Q1',
    file_url: null,
    thumbnail_url: null,
    created_at: '2026-03-31T12:00:00Z',
    updated_at: '2026-03-31T12:00:00Z',
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

describe('receipt page gate 6', () => {
  beforeEach(() => {
    updateDocument.mockReset();
    updateDocument.mockResolvedValue(receipt());
    vi.mocked(api.getDocument).mockResolvedValue(receipt());
  });

  it('does not preselect a type or a cited number, and confirm stays disabled', async () => {
    renderPage();

    const confirm = await screen.findByRole('button', { name: 'Está correto' });
    expect(confirm).toBeDisabled();
    expect(screen.getByLabelText('Tipo de documento')).toHaveValue('unclassified');
    expect(screen.getByRole('button', { name: 'Usar sugestão: Fatura' })).toBeInTheDocument();

    fireEvent.click(confirm);
    expect(updateDocument).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Editar dados' }));
    expect(screen.getByLabelText('Tipo de documento')).toHaveValue('unclassified');
    expect(screen.getByLabelText('N.º da fatura')).toHaveValue('');
    const save = screen.getByRole('button', { name: 'Guardar e confirmar' });
    expect(save).toBeDisabled();

    fireEvent.click(save);
    expect(updateDocument).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('Tipo de documento'), { target: { value: 'NC' } });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => expect(updateDocument).toHaveBeenCalledTimes(1));
    expect(updateDocument).toHaveBeenCalledWith(
      'doc-v6',
      expect.objectContaining({
        document_type: 'NC',
        invoice_number: null,
        status: 'ready',
      }),
    );
    const payload = updateDocument.mock.calls[0][1] as { invoice_number: string | null };
    expect(payload.invoice_number).not.toBe('FT A/12');
  });

  it('confirms a non-QR receipt only after an explicit type pick, without the suggested number', async () => {
    renderPage();
    const confirm = await screen.findByRole('button', { name: 'Está correto' });
    fireEvent.change(screen.getByLabelText('Tipo de documento'), { target: { value: 'NC' } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(updateDocument).toHaveBeenCalledTimes(1));
    expect(updateDocument).toHaveBeenCalledWith('doc-v6', {
      document_type: 'NC',
      status: 'ready',
    });
  });

  it('keeps Está correto for a receipt that already has a concrete type', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      receipt({ document_type: 'FT', invoice_number: 'FT A/1', status: 'needs_review' }),
    );
    renderPage();
    const confirm = await screen.findByRole('button', { name: 'Está correto' });
    expect(screen.queryByLabelText('Tipo de documento')).not.toBeInTheDocument();
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(updateDocument).toHaveBeenCalledWith('doc-v6', { status: 'ready' }),
    );
  });
});
