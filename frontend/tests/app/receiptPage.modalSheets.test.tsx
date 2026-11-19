import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import { LAYERS } from '@/components/layout/layers';
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

const DELETE_ERROR = 'Não foi possível remover. Tente novamente.';

function receipt(overrides: Partial<Document> = {}): Document {
  return {
    id: 'doc-sheets',
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
    file_url: '/api/documents/doc-sheets/file',
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

async function openDelete() {
  renderPage();
  const opener = await screen.findByRole('button', { name: 'Remover recibo' });
  opener.focus();
  fireEvent.click(opener);
  return { opener, dialog: screen.getByRole('alertdialog', { name: 'Remover recibo' }) };
}

const key = (k: string, shiftKey = false) => fireEvent.keyDown(document.activeElement!, { key: k, shiftKey });

describe('receipt page sheets: keyboard and focus', () => {
  beforeEach(() => {
    getUseParamsMock().mockReturnValue({ id: 'doc-sheets' });
    vi.mocked(api.getDocument).mockResolvedValue(receipt());
    vi.mocked(api.deleteDocument).mockReset();
  });

  it('focuses Cancelar in the delete confirm and traps Tab and Shift+Tab', async () => {
    const { dialog } = await openDelete();
    const cancel = within(dialog).getByRole('button', { name: 'Cancelar' });
    const remove = within(dialog).getByRole('button', { name: 'Remover' });
    const close = within(dialog).getByRole('button', { name: 'Fechar' });
    expect(cancel).toHaveFocus();
    key('Tab');
    expect(remove).toHaveFocus();
    key('Tab');
    expect(close).toHaveFocus();
    key('Tab', true);
    expect(remove).toHaveFocus();
  });

  it.each([
    ['Escape', () => key('Escape')],
    ['a backdrop tap', () => fireEvent.click(screen.getByRole('alertdialog').parentElement!)],
  ])('closes the delete confirm on %s and returns focus to Remover recibo', async (_, act) => {
    const { opener } = await openDelete();
    act();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
    expect(api.deleteDocument).not.toHaveBeenCalled();
  });

  it.each([
    ['Escape', () => key('Escape')],
    ['a backdrop tap', () => fireEvent.click(screen.getByRole('dialog').parentElement!)],
  ])('closes the category sheet on %s and returns focus to the chip', async (_, act) => {
    renderPage();
    const chip = await screen.findByRole('button', { name: /Serviços/ });
    chip.focus();
    fireEvent.click(chip);
    const dialog = screen.getByRole('dialog', { name: 'Categoria' });
    expect(within(dialog).getByRole('button', { name: 'Fechar' })).toHaveFocus();
    act();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(chip).toHaveFocus();
  });

  it('returns focus to the chip after a category is picked', async () => {
    vi.mocked(api.updateDocument).mockReturnValue(new Promise(() => {}));
    renderPage();
    const chip = await screen.findByRole('button', { name: /Serviços/ });
    chip.focus();
    fireEvent.click(chip);
    fireEvent.click(within(screen.getByRole('dialog')).getAllByRole('button')[1]);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(chip).toHaveFocus();
  });
});

describe('receipt page delete confirm: failed DELETE', () => {
  beforeEach(() => {
    getUseParamsMock().mockReturnValue({ id: 'doc-sheets' });
    vi.mocked(api.getDocument).mockResolvedValue(receipt());
    vi.mocked(api.deleteDocument).mockReset();
  });

  it.each([
    ['404', { status: 404, message: 'Not Found' }],
    ['409', { status: 409, message: 'Conflict' }],
    ['503', { status: 503, message: 'Service Unavailable' }],
    ['offline', new TypeError('Failed to fetch')],
  ])('keeps the sheet open with the PT-PT error on %s, and Remover retries', async (_, failure) => {
    vi.mocked(api.deleteDocument).mockRejectedValueOnce(failure).mockResolvedValueOnce(undefined as never);
    const { dialog } = await openDelete();
    const remove = within(dialog).getByRole('button', { name: 'Remover' });

    fireEvent.click(remove);
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(DELETE_ERROR);
    expect(screen.getByRole('alertdialog', { name: 'Remover recibo' })).toBe(dialog);
    expect(remove).toBeEnabled();
    expect(api.deleteDocument).toHaveBeenCalledTimes(1);

    fireEvent.click(remove);
    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  });

  it('sends one DELETE per tap, even on a double tap', async () => {
    let fail!: (e: unknown) => void;
    vi.mocked(api.deleteDocument).mockReturnValue(new Promise((_, reject) => (fail = reject)));
    const { dialog } = await openDelete();
    const remove = within(dialog).getByRole('button', { name: 'Remover' });

    fireEvent.click(remove);
    fireEvent.click(remove);
    key('Escape');
    expect(api.deleteDocument).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('alertdialog')).toBe(dialog);

    fail({ status: 503, message: 'Service Unavailable' });
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(DELETE_ERROR);
  });

  it('clears the error when the confirm is reopened', async () => {
    vi.mocked(api.deleteDocument).mockRejectedValue({ status: 503, message: 'Service Unavailable' });
    const { opener, dialog } = await openDelete();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remover' }));
    await within(dialog).findByRole('alert');
    key('Escape');
    fireEvent.click(opener);
    expect(within(screen.getByRole('alertdialog')).queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('receipt page image viewer layer', () => {
  beforeEach(() => {
    getUseParamsMock().mockReturnValue({ id: 'doc-sheets' });
    vi.mocked(api.getDocument).mockResolvedValue(receipt());
  });

  it('renders fullscreen on <body> at the viewer layer, and Escape closes only it', async () => {
    const { container } = renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Ver em ecrã inteiro' }));
    const close = screen.getByRole('button', { name: 'Fechar ecrã inteiro' });
    const overlay = close.parentElement!;
    expect(overlay.parentElement).toBe(document.body);
    expect(container.contains(overlay)).toBe(false);
    expect(overlay).toHaveClass(LAYERS.viewer);
    expect(close).toHaveFocus();

    key('Escape');
    expect(screen.queryByRole('button', { name: 'Fechar ecrã inteiro' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remover recibo' })).toBeInTheDocument();
  });
});
