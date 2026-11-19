import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axe from 'axe-core';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import type { Document, DocumentListResponse } from '@/lib/api';
import { PT_DATE_INVALID } from '@/lib/ptDate';

vi.mock('@/lib/api', () => ({
  api: {
    getDocuments: vi.fn(),
  },
}));

import { api } from '@/lib/api';
import ReceiptsPage from '@/app/receipts/page';

function receipt(): Document {
  return {
    id: 'doc-date',
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
    document_date: '2026-10-15',
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
    period_tag: '2026-10',
    quarter_tag: '2026-Q4',
    file_url: null,
    thumbnail_url: null,
    created_at: '2026-10-15T12:00:00Z',
    updated_at: '2026-10-15T12:00:00Z',
  };
}

function list(documents: Document[]): DocumentListResponse {
  return { documents, total: documents.length, page: 1, page_size: 50, has_more: false };
}

function dateParamsSent() {
  return vi.mocked(api.getDocuments).mock.calls.map(([params]) => [params?.date_from, params?.date_to]);
}

async function renderPage() {
  const view = render(
    <AuthProvider>
      <ReceiptsPage />
    </AuthProvider>,
  );
  await screen.findByRole('button', { name: 'Atualizar lista' });
  return view;
}

describe('receipts date filters read dd/mm/aaaa', () => {
  beforeEach(() => {
    vi.mocked(api.getDocuments).mockReset();
    vi.mocked(api.getDocuments).mockResolvedValue(list([receipt()]));
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ email: 'qa@example.com', id: 'ignored' }));
  });

  afterEach(() => {
    localStorage.removeItem(DEMO_AUTH_KEY);
  });

  it('shows dd/mm/aaaa and never the US mm/dd/yyyy', async () => {
    const { container } = await renderPage();
    for (const name of ['De', 'Até']) {
      const input = screen.getByLabelText(name);
      expect(input).toHaveAttribute('type', 'text');
      expect(input).toHaveAttribute('placeholder', 'dd/mm/aaaa');
      expect(input).toHaveAttribute('inputmode', 'numeric');
      expect(input).toHaveAttribute('autocomplete', 'off');
      expect(input).toHaveAccessibleDescription('dd/mm/aaaa');
    }
    expect(container.querySelector('input[type="date"]')).toBeNull();
    expect(container.innerHTML).not.toMatch(/mm\/dd\/yyyy/i);
  });

  it('filters 15/10/2026 as 2026-10-15', async () => {
    await renderPage();
    const from = screen.getByLabelText('De');
    fireEvent.change(from, { target: { value: '15102026' } });
    expect(from).toHaveValue('15/10/2026');
    fireEvent.blur(from);
    await waitFor(() => expect(dateParamsSent()).toContainEqual(['2026-10-15', undefined]));

    const to = screen.getByLabelText('Até');
    fireEvent.change(to, { target: { value: '31/10/2026' } });
    fireEvent.blur(to);
    await waitFor(() => expect(dateParamsSent()).toContainEqual(['2026-10-15', '2026-10-31']));
    expect(from).not.toHaveAttribute('aria-invalid');
  });

  it('shows an error for 32/13/2026 and does not send it to the API', async () => {
    await renderPage();
    const callsBefore = vi.mocked(api.getDocuments).mock.calls.length;
    const from = screen.getByLabelText('De');
    fireEvent.change(from, { target: { value: '32/13/2026' } });
    fireEvent.blur(from);

    expect(from).toHaveAttribute('aria-invalid', 'true');
    expect(from).toHaveAccessibleDescription(PT_DATE_INVALID);
    expect(from.className).toContain('border-[color:var(--ff-danger)]');
    const message = screen.getByText(PT_DATE_INVALID);
    expect(message).toHaveClass('text-sm');
    // Let any refetch that would have been triggered run.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(vi.mocked(api.getDocuments).mock.calls.length).toBe(callsBefore);
    for (const [dateFrom] of dateParamsSent()) {
      expect(dateFrom).toBeUndefined();
    }

    fireEvent.change(from, { target: { value: '15/10/2026' } });
    fireEvent.blur(from);
    expect(from).not.toHaveAttribute('aria-invalid');
    await waitFor(() => expect(dateParamsSent()).toContainEqual(['2026-10-15', undefined]));
  });

  it('keeps the 44 px tap target', async () => {
    await renderPage();
    for (const name of ['De', 'Até']) {
      expect(screen.getByLabelText(name)).toHaveClass('min-h-11', 'lg:min-h-0');
    }
  });

  it('passes axe label checks, also with an error shown', async () => {
    const { container } = await renderPage();
    const from = screen.getByLabelText('De');
    const run = () =>
      axe.run(container, { runOnly: { type: 'rule', values: ['label', 'aria-valid-attr-value', 'label-title-only'] } });
    expect((await run()).violations).toEqual([]);
    fireEvent.change(from, { target: { value: '32/13/2026' } });
    fireEvent.blur(from);
    expect((await run()).violations).toEqual([]);
  });
});
