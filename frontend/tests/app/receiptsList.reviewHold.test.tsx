import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import type { Document, DocumentListResponse } from '@/lib/api';

vi.mock('@/lib/api', () => ({
  api: {
    getDocuments: vi.fn(),
  },
}));

import { api } from '@/lib/api';
import ReceiptsPage from '@/app/receipts/page';

function receipt(overrides: Partial<Document> = {}): Document {
  return {
    id: 'doc-plain',
    user_id: 'user-1',
    status: 'needs_review',
    storage_key: 'efatura/user/doc',
    original_filename: 'FT_A_5.efatura',
    mime_type: 'application/vnd.invoflow.efatura+json',
    file_size: null,
    vendor_name: 'Loja do Bairro',
    vendor_nif: '296123456',
    invoice_number: 'FT A/5',
    document_type: 'FT',
    suggested_type: null,
    suggested_invoice_number: null,
    at_document_type: 'FT',
    at_invoice_number: null,
    linked_at_pair: null,
    efatura_review: null,
    document_date: '2026-04-01',
    net_amount: '10.00',
    vat_amount: '2.30',
    gross_amount: '12.30',
    vat_rate: '23.00',
    ocr_confidence: null,
    field_confidence: null,
    validation_warnings: [],
    review_notes: null,
    expense_category: 'utilities',
    irs_sector: null,
    deductible_pct: 100,
    deductible_pct_override: null,
    period_tag: '2026-04',
    quarter_tag: '2026-Q2',
    file_url: null,
    thumbnail_url: null,
    created_at: '2026-04-01T12:00:00Z',
    updated_at: '2026-04-01T12:00:00Z',
    ...overrides,
  };
}

function list(documents: Document[]): DocumentListResponse {
  return { documents, total: documents.length, page: 1, page_size: 50, has_more: false };
}

function renderPage() {
  localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ email: 'qa@example.com', id: 'ignored' }));
  return render(
    <AuthProvider>
      <ReceiptsPage />
    </AuthProvider>,
  );
}

describe('receipts list row held for review', () => {
  beforeEach(() => {
    vi.mocked(api.getDocuments).mockResolvedValue(
      list([
        receipt({
          id: 'doc-held',
          vendor_name: 'Mercearia Central',
          efatura_review: {
            related_document_id: 'scan-1',
            related_invoice_number: 'ft a/5',
            related_vendor_name: 'Mercearia Central',
          },
        }),
        receipt({ id: 'doc-plain', vendor_name: 'Oficina do Bairro' }),
      ]),
    );
  });

  afterEach(() => {
    localStorage.removeItem(DEMO_AUTH_KEY);
  });

  it('shows the badge and names the related receipt', async () => {
    renderPage();

    const held = await screen.findByRole('link', { name: /Mercearia Central/ });
    expect(within(held).getByText('Em revisão')).toBeVisible();
    const note = within(held).getByText(/Pode corresponder ao recibo ft a\/5 \(Mercearia Central\)/);
    expect(note).toHaveTextContent('Reveja os dois.');
    expect(held).toHaveAccessibleName(/Em revisão: Pode corresponder ao recibo ft a\/5/);

    const plain = screen.getByRole('link', { name: /Oficina do Bairro/ });
    expect(within(plain).queryByText('Em revisão')).not.toBeInTheDocument();
  });

  it('shows the held row its own number next to the related receipt', async () => {
    vi.mocked(api.getDocuments).mockResolvedValue(
      list([
        receipt({
          id: 'doc-held',
          invoice_number: 'FT A/5',
          efatura_review: {
            related_document_id: 'at-edited',
            related_invoice_number: 'FT A/5',
            related_vendor_name: 'Loja do Bairro',
          },
        }),
        receipt({ id: 'doc-plain', vendor_name: 'Oficina do Bairro', invoice_number: 'FT B/9' }),
      ]),
    );
    renderPage();

    const held = await screen.findByRole('link', { name: /Em revisão/ });
    const line = within(held).getByText('Em revisão').parentElement!;
    expect(within(line).getByText('e-Fatura FT A/5')).toBeVisible();
    expect(within(line).getByText(/Pode corresponder ao recibo FT A\/5 \(Loja do Bairro\)/)).toBeVisible();
    expect(held).toHaveAccessibleName(
      /e-Fatura n\.º FT A\/5, Em revisão: Pode corresponder ao recibo FT A\/5 \(Loja do Bairro\)/,
    );

    const plain = screen.getByRole('link', { name: /Oficina do Bairro/ });
    expect(within(plain).queryByText(/e-Fatura FT B\/9/)).not.toBeInTheDocument();
  });

  it('names a related e-Fatura row a user renumbered by its AT number', async () => {
    vi.mocked(api.getDocuments).mockResolvedValue(
      list([
        receipt({
          id: 'doc-held',
          invoice_number: 'FT E/5',
          efatura_review: {
            related_document_id: 'at-edited',
            related_invoice_number: 'FT E/5',
            related_vendor_name: 'Loja do Bairro',
            related_is_efatura: true,
            related_original_number: 'FT e/5',
          },
        }),
      ]),
    );
    renderPage();

    const held = await screen.findByRole('link', { name: /Em revisão/ });
    expect(
      within(held).getByText(
        'Pode corresponder ao documento do e-Fatura FT e/5 (Loja do Bairro), que foi renumerado para FT E/5. Reveja os dois.',
      ),
    ).toBeVisible();
    expect(within(held).queryByText(/ao recibo/)).not.toBeInTheDocument();
  });

  it('shows an unresolved e-Fatura clash as a badge with its message', async () => {
    const message = 'A fatura n.º FT A/5 do e-Fatura não foi importada: corresponde a este recibo e a outro.';
    vi.mocked(api.getDocuments).mockResolvedValue(
      list([
        receipt({
          id: 'doc-clash',
          vendor_name: 'Papelaria',
          validation_warnings: [
            { code: 'efatura_not_imported', message, severity: 'warning', field: 'invoice_number' },
          ],
        }),
        receipt({ id: 'doc-plain', vendor_name: 'Oficina do Bairro' }),
      ]),
    );
    renderPage();

    const row = await screen.findByRole('link', { name: /Papelaria/ });
    expect(within(row).getByText('e-Fatura por resolver')).toBeVisible();
    expect(within(row).getByText(message)).toBeVisible();
    expect(row).toHaveAccessibleName(/e-Fatura por resolver: A fatura n\.º FT A\/5/);
    const plain = screen.getByRole('link', { name: /Oficina do Bairro/ });
    expect(within(plain).queryByText('e-Fatura por resolver')).not.toBeInTheDocument();
  });

  it('puts the review note on its own wrapping line on narrow screens', async () => {
    renderPage();

    const held = await screen.findByRole('link', { name: /Mercearia Central/ });
    const note = within(held).getByText(/Pode corresponder ao recibo/);
    let node: HTMLElement | null = note;
    while (node && node !== held) {
      expect(node.classList.contains('truncate')).toBe(false);
      node = node.parentElement;
    }
    expect(note.classList.contains('break-words')).toBe(true);
    const line = note.parentElement!;
    expect(line.classList.contains('flex-wrap')).toBe(true);
    expect(within(line).getByText('Em revisão')).toBeInTheDocument();
  });
});
