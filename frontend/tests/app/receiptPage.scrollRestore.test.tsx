import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import { resetScrollMemoryForTests, takeRestoreDecision } from '@/lib/mainScroll';
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

async function renderPage() {
  localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ email: 'qa@example.com', id: 'ignored' }));
  render(
    <AuthProvider>
      <ReceiptDetailPage />
    </AuthProvider>,
  );
  await screen.findByRole('button', { name: 'Está correto' });
  // The receipt screen itself has mounted.
  takeRestoreDecision('/receipts/doc-mobile');
}

/** The list keeps its scroll position on the way back from a receipt, as the back button would. */
describe('receipt page: back to the list where it was left', () => {
  beforeEach(() => {
    resetScrollMemoryForTests();
    getUseParamsMock().mockReturnValue({ id: 'doc-mobile' });
    vi.mocked(api.getDocument).mockResolvedValue(receipt());
    vi.mocked(api.updateDocument).mockResolvedValue(receipt({ status: 'ready' }));
    vi.mocked(api.deleteDocument).mockResolvedValue(undefined as never);
  });

  it('after confirming', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Está correto' }));
    await waitFor(() => expect(api.updateDocument).toHaveBeenCalled());
    await waitFor(() => expect(takeRestoreDecision('/receipts')).toBe(true));
  });

  it('after editing and saving', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Editar dados' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar e confirmar' }));
    await waitFor(() => expect(api.updateDocument).toHaveBeenCalled());
    await waitFor(() => expect(takeRestoreDecision('/receipts')).toBe(true));
  });

  it('after removing the receipt', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Remover recibo' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remover' }));
    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalled());
    await waitFor(() => expect(takeRestoreDecision('/receipts')).toBe(true));
  });

  it('not when the save fails and the screen stays on the receipt', async () => {
    vi.mocked(api.updateDocument).mockRejectedValue({ status: 503, message: 'Service Unavailable' });
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Está correto' }));
    await screen.findByRole('alert');
    expect(takeRestoreDecision('/receipts')).toBe(false);
  });
});
