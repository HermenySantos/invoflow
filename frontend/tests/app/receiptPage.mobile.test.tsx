import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import axe from 'axe-core';
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
    expect(bar.className).toContain('bottom-0');
    expect(bar.className).not.toMatch(/\bfixed\b|\bbottom-16\b/);
    expect(bar.parentElement!.className).toContain('min-h-[calc(100dvh-var(--ff-nav-h))]');
    // Cancels the scroll area's pb-4, so the bar rests on the nav at the end of the page too.
    expect(bar.parentElement).toHaveClass('-mb-4');
  });

  it('from lg, keeps a sticky image column and the action bar in the form column', async () => {
    renderPage();
    const image = await screen.findByAltText('Recibo de Padaria Central');
    const bar = screen.getByTestId('receipt-action-bar');
    const imageCol = image.closest('[data-testid="receipt-image-column"]') as HTMLElement;
    const page = bar.parentElement as HTMLElement;

    expect(imageCol).toBeTruthy();
    expect(page).toContainElement(imageCol);
    expect(page.className).toContain('lg:grid-cols-[352px_minmax(24.75rem,36rem)_1fr]');
    expect(page.className).toContain('xl:grid-cols-[510px_minmax(24.75rem,36rem)_1fr]');
    expect(page.className).not.toContain('lg:w-[100cqw]');
    const frame = screen.getByTestId('receipt-image-frame');
    expect(frame).toHaveClass('lg:w-full', 'aspect-[4/3]', 'lg:max-h-[calc(100dvh-8rem)]', 'lg:min-h-[180px]');
    expect(frame.className).toContain('lg:[aspect-ratio:var(--receipt-image-aspect,3/4)]');
    expect(imageCol).toHaveClass('lg:z-[45]');
    expect(page.querySelector('header')).toHaveClass('lg:col-span-full');
    expect(image.parentElement?.className ?? '').not.toContain('max-h-');
    expect(page.className).toContain('lg:gap-x-6');
    expect(imageCol).toHaveClass('lg:sticky', 'lg:col-start-1', 'lg:row-span-2');
    expect(bar).toHaveClass('lg:col-start-2', 'lg:row-start-3');
    expect(imageCol.contains(bar)).toBe(false);
  });

  it('follows a wide image at lg and stacks the deductible label under 360px', async () => {
    renderPage();
    const img = (await screen.findByAltText('Recibo de Padaria Central')) as HTMLImageElement;
    Object.defineProperty(img, 'naturalWidth', { configurable: true, value: 1600 });
    Object.defineProperty(img, 'naturalHeight', { configurable: true, value: 900 });
    fireEvent.load(img);

    const frame = screen.getByTestId('receipt-image-frame');
    expect(frame.style.getPropertyValue('--receipt-image-aspect')).toBe(String(1600 / 900));
    expect(frame).toHaveClass('lg:w-full', 'lg:min-w-[320px]', 'lg:min-h-[180px]');
    expect(frame.className).not.toContain('lg:w-[min(478px');
    const shell = screen.getByTestId('receipt-action-bar').parentElement as HTMLElement;
    expect(shell).toHaveClass('lg:grid-cols-[352px_minmax(24.75rem,36rem)_1fr]');
    expect(shell.className).not.toContain('max-content');
    expect(screen.getByText('IVA dedutível').closest('label')).toHaveClass(
      'max-[359px]:flex-col',
      'max-[359px]:items-stretch',
    );
  });

  it('puts the receipt pane in the document while the receipt is still loading, before the action bar', () => {
    vi.mocked(api.getDocument).mockReturnValue(new Promise(() => {}));
    renderPage();
    const pane = document.querySelector('.receipt-pane');
    expect(pane).toBeTruthy();
    expect(pane?.closest('main')).toHaveAttribute('id', 'main-content');
    expect(screen.queryByTestId('receipt-action-bar')).not.toBeInTheDocument();
  });

  it('pads the scrollport so the sticky action bar cannot cover the focused control', () => {
    const css = readFileSync(path.resolve(__dirname, '../../app/globals.css'), 'utf8');
    expect(css).toContain('scroll-padding-top: 4rem');
    expect(css).toContain('scroll-padding-bottom: calc(var(--receipt-bar-h, 13rem) + 1rem)');
    expect(css).toContain('[data-testid="receipt-form-column"]:focus-within');
    expect(css).not.toContain('scroll-padding-bottom: 13rem');
    expect(css).toMatch(/main#main-content:has\(\.receipt-pane\)\s*\{[^}]*container-type:\s*inline-size/);
  });

  it('labels the image and the header buttons in Portuguese', async () => {
    renderPage();
    expect(await screen.findByAltText('Recibo de Padaria Central')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Voltar aos recibos' })).toHaveAttribute('href', '/receipts');
    expect(screen.getByRole('button', { name: 'Remover recibo' })).toBeInTheDocument();
  });

  // Inside #main-content at the nav's own z-50, the sheet sat under the nav, so "Remover" hit "IVA".
  it.each([
    ['Remover recibo', 'alertdialog', 'Remover recibo'],
    [/Serviços/, 'dialog', 'Categoria'],
  ] as const)('mounts the %s overlay on <body>, above the nav', async (opener, role, title) => {
    const { container } = renderPage();
    fireEvent.click(await screen.findByRole('button', { name: opener }));
    const dialog = screen.getByRole(role, { name: title });
    const overlay = dialog.parentElement as HTMLElement;

    expect(overlay.parentElement).toBe(document.body);
    expect(container.contains(overlay)).toBe(false);
    expect(overlay).toHaveClass('fixed', 'inset-0', 'z-[60]');
  });

  it('gives the delete confirm 44 px buttons at every width', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Remover recibo' }));
    const dialog = screen.getByRole('alertdialog', { name: 'Remover recibo' });
    expect(within(dialog).getByRole('button', { name: 'Remover' })).toHaveClass('min-h-11');
    expect(within(dialog).getByRole('button', { name: 'Cancelar' })).toHaveClass('min-h-11');
  });

  it('styles Remover as the dark danger fill and states only what removal hides', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Remover recibo' }));
    const dialog = screen.getByRole('alertdialog', { name: 'Remover recibo' });
    const remove = within(dialog).getByRole('button', { name: 'Remover' });

    expect(remove).toHaveClass('btn-danger');
    expect(remove.className).not.toMatch(/\bbg-red-\d+/);
    expect(dialog).toHaveTextContent(
      /^Remover recibo\s*O recibo deixa de aparecer na lista, no resumo e na exportação\.\s*CancelarRemover$/,
    );
    expect(document.body.textContent).not.toMatch(/lei exige|como a lei|original fica guardado/i);
  });

  it('labels every field of the edit form', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar dados' }));

    expect(screen.getByLabelText('Data do documento')).toHaveAttribute('id', 'edit-document-date');
    for (const name of ['Fornecedor', 'Total (€)', 'IVA (€)']) {
      expect(screen.getByLabelText(name)).toBeInTheDocument();
    }
    const form = screen.getByRole('heading', { name: 'Editar dados' }).closest('.card') as HTMLElement;
    const { violations } = await axe.run(form, { runOnly: { type: 'rule', values: ['label'] } });
    expect(violations).toEqual([]);
  });

  it('falls back to a plain label when the vendor is unknown', async () => {
    vi.mocked(api.getDocument).mockResolvedValue(receipt({ vendor_name: null }));
    renderPage();
    expect(await screen.findByAltText('Recibo')).toBeInTheDocument();
  });
});
