import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import type { Document, DocumentListResponse } from '@/lib/api';
import { EXPENSE_CATEGORY_LIST } from '@/lib/categories';

vi.mock('@/lib/api', () => ({
  api: {
    getDocuments: vi.fn(),
  },
}));

import { api } from '@/lib/api';
import ReceiptsPage from '@/app/receipts/page';

function receipt(): Document {
  return {
    id: 'doc-tap',
    user_id: 'user-1',
    status: 'ready',
    storage_key: 'user/recibo.jpg',
    original_filename: 'recibo.jpg',
    mime_type: 'image/jpeg',
    file_size: 1200,
    vendor_name: 'Padaria Central',
    vendor_nif: '123456002',
    invoice_number: 'FT A/7',
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

function list(documents: Document[]): DocumentListResponse {
  return { documents, total: documents.length, page: 1, page_size: 50, has_more: false };
}

/** 44 px (min-h-11) below lg, the previous desktop size from lg up. */
function expectMobileTapTarget(element: HTMLElement, desktop: string) {
  expect(element.classList.contains('min-h-11')).toBe(true);
  expect(element.classList.contains(desktop)).toBe(true);
}

describe('receipts list tap targets on a phone', () => {
  beforeEach(() => {
    vi.mocked(api.getDocuments).mockResolvedValue(list([receipt()]));
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ email: 'qa@example.com', id: 'ignored' }));
    render(
      <AuthProvider>
        <ReceiptsPage />
      </AuthProvider>,
    );
  });

  afterEach(() => {
    localStorage.removeItem(DEMO_AUTH_KEY);
  });

  it('gives every filter chip 44 px', async () => {
    expectMobileTapTarget(await screen.findByRole('button', { name: 'Todos' }), 'lg:min-h-10');
    for (const category of EXPENSE_CATEGORY_LIST) {
      expectMobileTapTarget(screen.getByRole('button', { name: category.label }), 'lg:min-h-10');
    }
  });

  it('wraps the chips from sm (landscape phone, 800x360) instead of cutting them at the column edge', async () => {
    const row = (await screen.findByRole('button', { name: 'Todos' })).parentElement!;
    // A phone held upright keeps the swipeable row.
    expect(row).toHaveClass('flex', 'overflow-x-auto', '-mx-4', 'px-4');
    expect(row).toHaveClass('sm:flex-wrap', 'sm:overflow-visible', 'sm:mx-0', 'sm:px-0');
    for (const chip of Array.from(row.children)) {
      expect(chip).toHaveClass('min-h-11');
    }
  });

  it("gives 'Atualizar lista' 44 px", async () => {
    expectMobileTapTarget(await screen.findByRole('button', { name: 'Atualizar lista' }), 'lg:min-h-0');
  });

  it('gives both date inputs 44 px', async () => {
    await screen.findByRole('button', { name: 'Atualizar lista' });
    expectMobileTapTarget(screen.getByLabelText('De'), 'lg:min-h-0');
    expectMobileTapTarget(screen.getByLabelText('Até'), 'lg:min-h-0');
  });

  it("gives 'Limpar filtros' 44 px", async () => {
    vi.mocked(api.getDocuments).mockResolvedValue(list([]));
    fireEvent.click(await screen.findByRole('button', { name: EXPENSE_CATEGORY_LIST[0].label }));
    expectMobileTapTarget(await screen.findByRole('button', { name: 'Limpar filtros' }), 'lg:min-h-0');
  });
});
