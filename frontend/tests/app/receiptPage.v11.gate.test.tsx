import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import { PRINTED_PAIR_LABEL, SERIES_MISMATCH_DETAIL, SERIES_OVERRIDE_WARNING } from '@/lib/reviewEdit';
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
    id: 'doc-v11',
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

describe('receipt page gate 11', () => {
  beforeEach(() => {
    updateDocument.mockReset();
    updateDocument.mockResolvedValue(receipt());
    getUseParamsMock().mockReset();
    getUseParamsMock().mockReturnValue({ id: 'doc-v11' });
    vi.mocked(api.getDocument).mockResolvedValue(receipt());
  });

  afterEach(() => {
    getUseParamsMock().mockReset();
    getUseParamsMock().mockImplementation(() => ({ id: 'doc-v11' }));
  });

  it.each(['NC.2026/5', 'NC.1', 'NC2026', 'NC001'])(
    'blocks %s on an FT and does not offer the checkbox',
    async (number) => {
      vi.mocked(api.getDocument).mockResolvedValue(
        receipt({ document_type: 'FT', invoice_number: number }),
      );
      renderPage();
      const confirm = await screen.findByRole('button', { name: 'Está correto' });
      expect(screen.getByText(SERIES_MISMATCH_DETAIL)).toBeInTheDocument();
      expect(screen.queryByText(SERIES_OVERRIDE_WARNING)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(PRINTED_PAIR_LABEL)).not.toBeInTheDocument();
      expect(confirm).toBeDisabled();
      fireEvent.click(confirm);
      expect(updateDocument).not.toHaveBeenCalled();
    },
  );

  it.each(['FT.2026/12', 'FT.12'])(
    'blocks %s on an NC and does not offer the checkbox',
    async (number) => {
      vi.mocked(api.getDocument).mockResolvedValue(
        receipt({ document_type: 'NC', invoice_number: number }),
      );
      renderPage();
      const confirm = await screen.findByRole('button', { name: 'Está correto' });
      expect(screen.getByText(SERIES_MISMATCH_DETAIL)).toBeInTheDocument();
      expect(screen.queryByLabelText(PRINTED_PAIR_LABEL)).not.toBeInTheDocument();
      expect(confirm).toBeDisabled();
      fireEvent.click(confirm);
      expect(updateDocument).not.toHaveBeenCalled();
    },
  );

  it('hides the checkbox for a legacy AT type with no QR number', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      receipt({
        document_type: 'FR',
        invoice_number: 'FT 2026/12',
        at_document_type: 'FR',
        at_invoice_number: null,
      }),
    );
    renderPage();
    const confirm = await screen.findByRole('button', { name: 'Está correto' });
    expect(screen.getByText(SERIES_MISMATCH_DETAIL)).toBeInTheDocument();
    expect(screen.queryByLabelText(PRINTED_PAIR_LABEL)).not.toBeInTheDocument();
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(updateDocument).not.toHaveBeenCalled();
  });

  it('refuses an unprefixed credit retype of a linked e-Fatura scan', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      receipt({
        status: 'ready',
        document_type: 'FT',
        invoice_number: 'FT A/12',
        at_document_type: 'FT',
        at_invoice_number: 'FT A/12',
      }),
    );
    renderPage();
    await screen.findByRole('button', { name: 'Está correto' });
    fireEvent.click(screen.getByRole('button', { name: 'Editar dados' }));
    fireEvent.change(screen.getByLabelText('Tipo de documento'), { target: { value: 'NC' } });
    fireEvent.change(screen.getByLabelText('N.º da fatura'), { target: { value: '2026/12' } });
    const save = screen.getByRole('button', { name: 'Guardar e confirmar' });
    expect(screen.getByText(SERIES_MISMATCH_DETAIL)).toBeInTheDocument();
    expect(screen.queryByLabelText(PRINTED_PAIR_LABEL)).not.toBeInTheDocument();
    expect(save).toBeDisabled();
    fireEvent.click(save);
    expect(updateDocument).not.toHaveBeenCalled();
  });
});
