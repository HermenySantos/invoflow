import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

function pageTree() {
  return (
    <AuthProvider>
      <ReceiptDetailPage />
    </AuthProvider>
  );
}

function renderPage() {
  localStorage.setItem(
    DEMO_AUTH_KEY,
    JSON.stringify({ email: 'qa@example.com', id: 'ignored' }),
  );
  return render(pageTree());
}

type Gate = {
  id: string;
  resolve: (doc: Document) => void;
  reject: (err: unknown) => void;
};

describe('receipt page gate 7', () => {
  beforeEach(() => {
    updateDocument.mockReset();
    updateDocument.mockResolvedValue(receipt());
    getUseParamsMock().mockReset();
    getUseParamsMock().mockReturnValue({ id: 'doc-v6' });
    vi.mocked(api.getDocument).mockResolvedValue(receipt());
  });

  afterEach(() => {
    getUseParamsMock().mockReset();
    getUseParamsMock().mockImplementation(() => ({ id: 'doc-v6' }));
  });

  it('shows a suggestion as text and never as a control', async () => {
    renderPage();
    const confirm = await screen.findByRole('button', { name: 'Está correto' });
    expect(confirm).toBeDisabled();
    expect(screen.queryByRole('button', { name: /Usar sugestão|Usar n/ })).not.toBeInTheDocument();
    expect(screen.getAllByText('Sugestão: Fatura').length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByText('Sugestão: Fatura')[0]);
    expect(screen.getByLabelText('Tipo de documento')).toHaveValue('unclassified');
    fireEvent.click(confirm);
    expect(updateDocument).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Editar dados' }));
    expect(screen.getByLabelText('N.º da fatura')).toHaveValue('');
    expect(screen.getByText('Sugestão de n.º FT A/12')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Usar/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Sugestão de n.º FT A/12'));
    expect(screen.getByLabelText('N.º da fatura')).toHaveValue('');
  });

  it('saves an unclassified receipt as a draft', async () => {
    renderPage();
    await screen.findByRole('button', { name: 'Está correto' });
    fireEvent.click(screen.getByRole('button', { name: 'Editar dados' }));

    fireEvent.change(screen.getByPlaceholderText('Who issued this receipt?'), {
      target: { value: 'Padaria Nova' },
    });
    const amounts = screen.getAllByPlaceholderText('0.00');
    fireEvent.change(amounts[0], { target: { value: '15.00' } });
    fireEvent.change(amounts[1], { target: { value: '2.30' } });

    const save = screen.getByRole('button', { name: 'Guardar' });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => expect(updateDocument).toHaveBeenCalledTimes(1));
    expect(updateDocument).toHaveBeenCalledWith(
      'doc-v6',
      expect.objectContaining({
        vendor_name: 'Padaria Nova',
        gross_amount: '15.00',
        vat_amount: '2.30',
        net_amount: '12.70',
        document_type: 'unclassified',
        invoice_number: null,
        status: 'needs_review',
      }),
    );
  });

  it('blocks a credit note whose number is an FT series, and shows the API message', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(receipt({ invoice_number: 'FT A/12' }));
    renderPage();
    const confirm = await screen.findByRole('button', { name: 'Está correto' });
    fireEvent.change(screen.getByLabelText('Tipo de documento'), { target: { value: 'NC' } });
    expect(screen.getByText(SERIES_MISMATCH_DETAIL)).toBeInTheDocument();
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(updateDocument).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Editar dados' }));
    fireEvent.change(screen.getByLabelText('Tipo de documento'), { target: { value: 'NC' } });
    const save = screen.getByRole('button', { name: 'Guardar e confirmar' });
    expect(save).toBeDisabled();
    expect(screen.getAllByText(SERIES_MISMATCH_DETAIL).length).toBeGreaterThan(0);
    fireEvent.click(save);
    expect(updateDocument).not.toHaveBeenCalled();
  });

  it('confirms when the stored number has no series prefix', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(receipt({ invoice_number: 'INV-100' }));
    renderPage();
    const confirm = await screen.findByRole('button', { name: 'Está correto' });
    fireEvent.change(screen.getByLabelText('Tipo de documento'), { target: { value: 'NC' } });
    expect(screen.queryByText(SERIES_MISMATCH_DETAIL)).not.toBeInTheDocument();
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(updateDocument).toHaveBeenCalledTimes(1));
    expect(updateDocument).toHaveBeenCalledWith('doc-v6', {
      document_type: 'NC',
      status: 'ready',
    });
  });

  it('ignores a stale fetch after the route changes', async () => {
    const pending: Gate[] = [];
    vi.mocked(api.getDocument).mockImplementation(
      (id: string) =>
        new Promise((resolve, reject) => {
          pending.push({ id, resolve, reject });
        }),
    );
    getUseParamsMock().mockReturnValue({ id: 'doc-a' });
    const view = renderPage();
    await waitFor(() => expect(pending.some((item) => item.id === 'doc-a')).toBe(true));

    getUseParamsMock().mockReturnValue({ id: 'doc-b' });
    view.rerender(pageTree());
    await waitFor(() => expect(pending.some((item) => item.id === 'doc-b')).toBe(true));

    await act(async () => {
      pending
        .filter((item) => item.id === 'doc-b')
        .forEach((item) => item.resolve(receipt({ id: 'doc-b', vendor_name: 'Loja B' })));
    });
    expect(await screen.findByText('Loja B')).toBeInTheDocument();

    await act(async () => {
      pending
        .filter((item) => item.id === 'doc-a')
        .forEach((item) =>
          item.resolve(
            receipt({
              id: 'doc-a',
              vendor_name: 'Loja A',
              document_type: 'FT',
              invoice_number: 'FT A/12',
            }),
          ),
        );
    });
    expect(screen.queryByText('Loja A')).not.toBeInTheDocument();
    expect(screen.getByText('Loja B')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Tipo de documento'), { target: { value: 'FS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Está correto' }));
    await waitFor(() => expect(updateDocument).toHaveBeenCalledTimes(1));
    expect(updateDocument).toHaveBeenCalledWith('doc-b', {
      document_type: 'FS',
      status: 'ready',
    });
  });

  it('drops the previous receipt when the next fetch fails', async () => {
    vi.mocked(api.getDocument).mockImplementation(async (id: string) => {
      if (id === 'doc-b') throw new Error('missing');
      return receipt({
        id: 'doc-a',
        vendor_name: 'Loja A',
        document_type: 'FT',
        invoice_number: 'FT A/1',
      });
    });
    getUseParamsMock().mockReturnValue({ id: 'doc-a' });
    const view = renderPage();
    expect(await screen.findByText('Loja A')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Está correto' })).toBeEnabled();

    getUseParamsMock().mockReturnValue({ id: 'doc-b' });
    view.rerender(pageTree());

    expect(await screen.findByText('Não foi possível carregar o recibo.')).toBeInTheDocument();
    expect(screen.queryByText('Loja A')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Está correto' })).not.toBeInTheDocument();
    expect(updateDocument).not.toHaveBeenCalled();
  });

  it('does not show a response whose id is not the route', async () => {
    const pending: Gate[] = [];
    vi.mocked(api.getDocument).mockImplementation(
      (id: string) =>
        new Promise((resolve, reject) => {
          pending.push({ id, resolve, reject });
        }),
    );
    getUseParamsMock().mockReturnValue({ id: 'doc-b' });
    renderPage();
    await waitFor(() => expect(pending.some((item) => item.id === 'doc-b')).toBe(true));

    await act(async () => {
      pending
        .filter((item) => item.id === 'doc-b')
        .forEach((item) =>
          item.resolve(receipt({ id: 'doc-a', vendor_name: 'Loja A', document_type: 'FT' })),
        );
    });

    expect(screen.queryByText('Loja A')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Está correto' })).not.toBeInTheDocument();
    expect(updateDocument).not.toHaveBeenCalled();
  });
});
