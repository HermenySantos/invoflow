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
    status: 'ready',
    storage_key: 'user/recibo.jpg',
    original_filename: 'recibo.jpg',
    mime_type: 'image/jpeg',
    file_size: 1200,
    vendor_name: 'Oficina do Bairro',
    vendor_nif: '123456002',
    invoice_number: 'FT 2026/16',
    document_type: 'FT',
    suggested_type: null,
    suggested_invoice_number: null,
    at_document_type: null,
    at_invoice_number: null,
    linked_at_pair: null,
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

function list(documents: Document[]): DocumentListResponse {
  return {
    documents,
    total: documents.length,
    page: 1,
    page_size: 50,
    has_more: false,
  };
}

function renderPage() {
  localStorage.setItem(
    DEMO_AUTH_KEY,
    JSON.stringify({ email: 'qa@example.com', id: 'ignored' }),
  );
  return render(
    <AuthProvider>
      <ReceiptsPage />
    </AuthProvider>,
  );
}

describe('receipts list linked e-Fatura pair', () => {
  beforeEach(() => {
    vi.mocked(api.getDocuments).mockResolvedValue(
      list([
        receipt({
          id: 'doc-linked',
          vendor_name: 'Café Central',
          invoice_number: 'FT2026/15',
          linked_at_pair: {
            document_type: 'FT',
            invoice_number: 'FT 2026/15',
          },
        }),
        receipt({
          id: 'doc-plain',
          vendor_name: 'Oficina do Bairro',
          linked_at_pair: null,
        }),
      ]),
    );
  });

  afterEach(() => {
    localStorage.removeItem(DEMO_AUTH_KEY);
  });

  it('shows the AT number on a linked row and omits it on an unlinked row', async () => {
    renderPage();

    const linked = await screen.findByRole('link', { name: /Café Central/ });
    expect(within(linked).getByText('e-Fatura FT 2026/15')).toBeInTheDocument();
    expect(linked).toHaveAccessibleName(/e-Fatura n\.º FT 2026\/15/);

    const plain = screen.getByRole('link', { name: /Oficina do Bairro/ });
    expect(within(plain).queryByText(/e-Fatura/)).not.toBeInTheDocument();
    expect(within(plain).queryByText('FT 2026/16')).not.toBeInTheDocument();
    expect(plain).not.toHaveAccessibleName(/e-Fatura/);
  });

  it('puts the linked number on its own row on narrow screens without truncating it', async () => {
    renderPage();

    const linked = await screen.findByRole('link', { name: /Café Central/ });
    const pair = within(linked).getByText('e-Fatura FT 2026/15');

    let node: HTMLElement | null = pair;
    while (node) {
      expect(node.classList.contains('truncate')).toBe(false);
      if (node === linked) break;
      node = node.parentElement;
    }

    const wrapper = pair.parentElement;
    expect(wrapper).not.toBeNull();
    expect(
      wrapper!.classList.contains('basis-full') || wrapper!.classList.contains('w-full'),
    ).toBe(true);
    expect(
      wrapper!.classList.contains('sm:basis-auto') || wrapper!.classList.contains('sm:w-auto'),
    ).toBe(true);

    const dot = within(wrapper!).getByText('·');
    expect(dot.classList.contains('hidden')).toBe(true);
    expect(dot.classList.contains('sm:inline')).toBe(true);
  });
});
