import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import { SERIES_MISMATCH_DETAIL } from '@/lib/reviewEdit';
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

const AT_PAIRS = [
  ['FR', 'FT 2026/12'],
  ['FR', 'FTR A/12'],
  ['FS', 'FT A/12'],
  ['FS', 'FR 1/5'],
  ['ND', 'NC A/3'],
] as const;

function receipt(overrides: Partial<Document> = {}): Document {
  return {
    id: 'doc-v8',
    user_id: 'user-1',
    status: 'needs_review',
    storage_key: 'user/recibo.jpg',
    original_filename: 'recibo.jpg',
    mime_type: 'image/jpeg',
    file_size: 1200,
    vendor_name: 'Ana Exemplo',
    vendor_nif: '123456002',
    invoice_number: null,
    document_type: 'unclassified',
    suggested_type: null,
    suggested_invoice_number: null,
    at_document_type: null,
    at_invoice_number: null,
    document_date: '2026-01-15',
    net_amount: '10.00',
    vat_amount: '2.30',
    gross_amount: '12.30',
    vat_rate: '23.00',
    ocr_confidence: '95.00',
    field_confidence: null,
    validation_warnings: [],
    review_notes: null,
    expense_category: 'utilities',
    irs_sector: null,
    deductible_pct: 100,
    deductible_pct_override: null,
    period_tag: '2026-01',
    quarter_tag: '2026-Q1',
    file_url: null,
    thumbnail_url: null,
    created_at: '2026-01-15T12:00:00Z',
    updated_at: '2026-01-15T12:00:00Z',
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

describe('receipt page gate 8', () => {
  beforeEach(() => {
    updateDocument.mockReset();
    updateDocument.mockResolvedValue(receipt());
    getUseParamsMock().mockReset();
    getUseParamsMock().mockReturnValue({ id: 'doc-v8' });
    vi.mocked(api.getDocument).mockResolvedValue(receipt());
  });

  afterEach(() => {
    getUseParamsMock().mockReset();
    getUseParamsMock().mockImplementation(() => ({ id: 'doc-v8' }));
  });

  it.each(AT_PAIRS)(
    'confirms a QR %s numbered %s without a series warning',
    async (code, number) => {
      vi.mocked(api.getDocument).mockResolvedValue(
        receipt({
          status: 'ready',
          document_type: code,
          invoice_number: number,
          at_document_type: code,
          at_invoice_number: number,
        }),
      );
      renderPage();
      const confirm = await screen.findByRole('button', { name: 'Está correto' });
      expect(screen.queryByText(SERIES_MISMATCH_DETAIL)).not.toBeInTheDocument();
      expect(confirm).toBeEnabled();
      fireEvent.click(confirm);
      await waitFor(() => expect(updateDocument).toHaveBeenCalledTimes(1));
      expect(updateDocument).toHaveBeenCalledWith('doc-v8', { status: 'ready' });
    },
  );

  it.each(AT_PAIRS)(
    'confirms an e-Fatura %s numbered %s',
    async (code, number) => {
      vi.mocked(api.getDocument).mockResolvedValue(
        receipt({
          mime_type: 'application/vnd.invoflow.efatura+json',
          document_type: code,
          invoice_number: number,
          at_document_type: code,
          at_invoice_number: number,
        }),
      );
      renderPage();
      const confirm = await screen.findByRole('button', { name: 'Está correto' });
      expect(confirm).toBeEnabled();
      expect(screen.queryByText(SERIES_MISMATCH_DETAIL)).not.toBeInTheDocument();
      fireEvent.click(confirm);
      await waitFor(() => expect(updateDocument).toHaveBeenCalledTimes(1));
      expect(updateDocument).toHaveBeenCalledWith('doc-v8', { status: 'ready' });
    },
  );

  it('saves an AT pair from the edit form', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      receipt({
        document_type: 'FR',
        invoice_number: 'FT 2026/12',
        at_document_type: 'FR',
        at_invoice_number: 'FT 2026/12',
      }),
    );
    renderPage();
    await screen.findByRole('button', { name: 'Está correto' });
    fireEvent.click(screen.getByRole('button', { name: 'Editar dados' }));
    const save = screen.getByRole('button', { name: 'Guardar e confirmar' });
    expect(save).toBeEnabled();
    expect(screen.queryByText(SERIES_MISMATCH_DETAIL)).not.toBeInTheDocument();
    fireEvent.click(save);
    await waitFor(() => expect(updateDocument).toHaveBeenCalledTimes(1));
    expect(updateDocument).toHaveBeenCalledWith(
      'doc-v8',
      expect.objectContaining({
        document_type: 'FR',
        invoice_number: 'FT 2026/12',
        status: 'ready',
      }),
    );
  });

  it('blocks an edit that leaves the AT pair for a mismatching type', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      receipt({
        document_type: 'FR',
        invoice_number: 'FT 2026/12',
        at_document_type: 'FR',
        at_invoice_number: 'FT 2026/12',
      }),
    );
    renderPage();
    await screen.findByRole('button', { name: 'Está correto' });
    fireEvent.click(screen.getByRole('button', { name: 'Editar dados' }));
    fireEvent.change(screen.getByLabelText('Tipo de documento'), { target: { value: 'NC' } });
    const save = screen.getByRole('button', { name: 'Guardar e confirmar' });
    expect(save).toBeDisabled();
    expect(screen.getByText(SERIES_MISMATCH_DETAIL)).toBeInTheDocument();
    fireEvent.click(save);
    expect(updateDocument).not.toHaveBeenCalled();
  });

  it.each(['frete 12', 'fr001', 'FS2026/12', 'FRA2026/12'])(
    'does not treat %s as a series on an FT',
    async (number) => {
      vi.mocked(api.getDocument).mockResolvedValue(
        receipt({ document_type: 'FT', invoice_number: number }),
      );
      renderPage();
      const confirm = await screen.findByRole('button', { name: 'Está correto' });
      expect(screen.queryByText(SERIES_MISMATCH_DETAIL)).not.toBeInTheDocument();
      expect(confirm).toBeEnabled();
      fireEvent.click(confirm);
      await waitFor(() => expect(updateDocument).toHaveBeenCalledWith('doc-v8', { status: 'ready' }));
    },
  );

  it.each(['N\u0421 A/5', '\u041DC A/5', '\uFF2E\uFF23 A/5'])(
    'blocks the lookalike number %s on an FT',
    async (number) => {
      vi.mocked(api.getDocument).mockResolvedValue(
        receipt({ document_type: 'FT', invoice_number: number }),
      );
      renderPage();
      const confirm = await screen.findByRole('button', { name: 'Está correto' });
      expect(screen.getByText(SERIES_MISMATCH_DETAIL)).toBeInTheDocument();
      expect(confirm).toBeDisabled();
      fireEvent.click(confirm);
      expect(updateDocument).not.toHaveBeenCalled();
    },
  );

  it('still blocks a legacy mismatch that did not come from AT', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      receipt({
        status: 'ready',
        document_type: 'NC',
        invoice_number: 'FT A/12',
        at_document_type: null,
        at_invoice_number: null,
      }),
    );
    renderPage();
    const confirm = await screen.findByRole('button', { name: 'Está correto' });
    expect(confirm).toBeDisabled();
    expect(screen.getByText(SERIES_MISMATCH_DETAIL)).toBeInTheDocument();
    fireEvent.click(confirm);
    expect(updateDocument).not.toHaveBeenCalled();
  });

  it('shows no Fatura suggestion when the reader found a credit signal', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      receipt({
        suggested_type: null,
        suggested_invoice_number: null,
        invoice_number: null,
      }),
    );
    renderPage();
    await screen.findByRole('button', { name: 'Está correto' });
    expect(screen.queryByText(/Sugestão: Fatura/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Sugestão de n.º FT/)).not.toBeInTheDocument();
  });
});
