import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    id: 'doc-v9',
    user_id: 'user-1',
    status: 'needs_review',
    storage_key: 'user/recibo.jpg',
    original_filename: 'recibo.jpg',
    mime_type: 'image/jpeg',
    file_size: 1200,
    vendor_name: 'Mercearia do Largo',
    vendor_nif: '123456002',
    invoice_number: null,
    document_type: 'FT',
    suggested_type: null,
    suggested_invoice_number: null,
    at_document_type: null,
    at_invoice_number: null,
    document_date: '2026-03-31',
    net_amount: '10.00',
    vat_amount: '2.30',
    gross_amount: '12.30',
    vat_rate: '23.00',
    ocr_confidence: '90.00',
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

describe('receipt page gate 9', () => {
  beforeEach(() => {
    updateDocument.mockReset();
    updateDocument.mockResolvedValue(receipt());
    getUseParamsMock().mockReset();
    getUseParamsMock().mockReturnValue({ id: 'doc-v9' });
    vi.mocked(api.getDocument).mockResolvedValue(receipt());
  });

  afterEach(() => {
    getUseParamsMock().mockReset();
    getUseParamsMock().mockImplementation(() => ({ id: 'doc-v9' }));
  });

  it.each(['Fr. 12', 'FRA 2026/12', 'FS2026/12'])(
    'does not treat %s as a series on an FT',
    async (number) => {
      vi.mocked(api.getDocument).mockResolvedValue(receipt({ invoice_number: number }));
      renderPage();
      const confirm = await screen.findByRole('button', { name: 'Está correto' });
      expect(screen.queryByText(SERIES_MISMATCH_DETAIL)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(PRINTED_PAIR_LABEL)).not.toBeInTheDocument();
      expect(confirm).toBeEnabled();
      fireEvent.click(confirm);
      await waitFor(() => expect(updateDocument).toHaveBeenCalledWith('doc-v9', { status: 'ready' }));
    },
  );

  it('asks before confirming a glued NC number on an FT', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(receipt({ invoice_number: 'NC2026/5' }));
    renderPage();
    const confirm = await screen.findByRole('button', { name: 'Está correto' });
    expect(screen.getByText(SERIES_MISMATCH_DETAIL)).toBeInTheDocument();
    expect(screen.getByText(SERIES_OVERRIDE_WARNING)).toBeInTheDocument();
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(updateDocument).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText(PRINTED_PAIR_LABEL));
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(updateDocument).toHaveBeenCalledTimes(1));
    expect(updateDocument).toHaveBeenCalledWith('doc-v9', {
      status: 'ready',
      accept_series_mismatch: true,
    });
  });

  it.each(['N\u200bC A/5', '\u0143\u0106 A/5', '\u0274\u1d04 A/5', '\ua4e0\ua4da A/5'])(
    'blocks the lookalike number %s until the printed pair is confirmed',
    async (number) => {
      vi.mocked(api.getDocument).mockResolvedValue(receipt({ invoice_number: number }));
      renderPage();
      const confirm = await screen.findByRole('button', { name: 'Está correto' });
      expect(screen.getByText(SERIES_MISMATCH_DETAIL)).toBeInTheDocument();
      expect(confirm).toBeDisabled();
      fireEvent.click(confirm);
      expect(updateDocument).not.toHaveBeenCalled();
    },
  );

  it('confirms an AT pair without the printed-pair checkbox', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      receipt({
        document_type: 'FR',
        invoice_number: 'FT 2026/12',
        at_document_type: 'FR',
        at_invoice_number: 'FT 2026/12',
      }),
    );
    renderPage();
    const confirm = await screen.findByRole('button', { name: 'Está correto' });
    expect(screen.queryByLabelText(PRINTED_PAIR_LABEL)).not.toBeInTheDocument();
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(updateDocument).toHaveBeenCalledWith('doc-v9', { status: 'ready' }));
  });

  it('shows an error and a retry when the response id is wrong', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(receipt({ id: 'other-doc', vendor_name: 'Outra loja' }));
    renderPage();
    expect(await screen.findByText('Não foi possível carregar o recibo.')).toBeInTheDocument();
    expect(screen.queryByText('Outra loja')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Está correto' })).not.toBeInTheDocument();
    const retry = screen.getByRole('button', { name: 'Tentar de novo' });

    vi.mocked(api.getDocument).mockResolvedValue(receipt());
    fireEvent.click(retry);
    expect(await screen.findByText('Mercearia do Largo')).toBeInTheDocument();
    expect(screen.queryByText('Não foi possível carregar o recibo.')).not.toBeInTheDocument();
  });

  it('shows an error and a retry when the load fails', async () => {
    vi.mocked(api.getDocument).mockRejectedValue(new Error('missing'));
    renderPage();
    expect(await screen.findByText('Não foi possível carregar o recibo.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar de novo' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Está correto' })).not.toBeInTheDocument();

    vi.mocked(api.getDocument).mockResolvedValue(receipt());
    fireEvent.click(screen.getByRole('button', { name: 'Tentar de novo' }));
    expect(await screen.findByRole('button', { name: 'Está correto' })).toBeEnabled();
  });
});
