import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import type { Document } from '@/lib/api';
import { getUseParamsMock } from '../navigationState';

vi.mock('@/lib/api', () => ({
  api: {
    getDocument: vi.fn(),
    getDocumentAuditTrail: vi.fn().mockResolvedValue({ entries: [], total: 0 }),
    updateDocument: vi.fn(),
    deleteDocument: vi.fn(),
  },
}));

import { api } from '@/lib/api';
import ReceiptDetailPage from '@/app/receipts/[id]/page';

function receipt(overrides: Partial<Document> = {}): Document {
  return {
    id: 'doc-mobile',
    user_id: 'user-1',
    status: 'needs_review',
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
    file_url: '/api/documents/doc-mobile/file',
    thumbnail_url: null,
    created_at: '2026-03-15T12:00:00Z',
    updated_at: '2026-03-15T12:00:00Z',
    ...overrides,
  };
}

function renderPage() {
  localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ email: 'qa@example.com', id: 'ignored' }));
  return render(
    <AuthProvider>
      <ReceiptDetailPage />
    </AuthProvider>,
  );
}

describe('receipt page on a phone', () => {
  beforeEach(() => {
    getUseParamsMock().mockReturnValue({ id: 'doc-mobile' });
    vi.mocked(api.getDocument).mockResolvedValue(receipt());
  });

  it('keeps the action bar in the page flow, stuck just above the bottom nav', async () => {
    renderPage();
    const button = await screen.findByRole('button', { name: 'Está correto' });
    const bar = button.closest('[data-testid="receipt-action-bar"]') as HTMLElement;

    // A fixed bar at a hard-coded offset covered the nav's top edge, and more of it
    // above Android's gesture bar; it also hid content whenever it grew taller.
    expect(bar.className).toContain('sticky');
    expect(bar.className).toContain('bottom-[var(--ff-nav-h)]');
    expect(bar.className).not.toMatch(/\bfixed\b|\bbottom-16\b/);
    expect(bar.parentElement!.className).toContain('min-h-[calc(100dvh-var(--ff-nav-h))]');
  });

  it('labels the image and the header buttons in Portuguese', async () => {
    renderPage();
    expect(await screen.findByAltText('Recibo de Padaria Central')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Voltar aos recibos' })).toHaveAttribute('href', '/receipts');
    expect(screen.getByRole('button', { name: 'Remover recibo' })).toBeInTheDocument();
  });

  it('falls back to a plain label when the vendor is unknown', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(receipt({ vendor_name: null }));
    renderPage();
    expect(await screen.findByAltText('Recibo')).toBeInTheDocument();
  });
});
