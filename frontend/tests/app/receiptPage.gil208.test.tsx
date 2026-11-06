import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
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

const BUSY =
  'Está a decorrer uma importação do e-Fatura nesta conta. As alterações não foram ' +
  'guardadas; tente guardar novamente dentro de momentos.';

function receipt(): Document {
  return {
    id: 'doc-gil208',
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
  };
}

describe('receipt page GIL-208 N-6', () => {
  beforeEach(() => {
    updateDocument.mockReset();
    getUseParamsMock().mockReturnValue({ id: 'doc-gil208' });
    vi.mocked(api.getDocument).mockResolvedValue(receipt());
  });

  it('shows a 503 from a save inside the fixed action bar, not under it', async () => {
    updateDocument.mockRejectedValue(new Error(BUSY));
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ email: 'qa@example.com', id: 'ignored' }));
    render(
      <AuthProvider>
        <ReceiptDetailPage />
      </AuthProvider>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Está correto' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(BUSY);
    const bar = screen.getByRole('button', { name: 'Está correto' }).closest('.fixed');
    expect(bar).not.toBeNull();
    expect(bar).toContainElement(alert);
  });
});
