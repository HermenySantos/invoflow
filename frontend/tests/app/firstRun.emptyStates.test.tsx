import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { BottomNav } from '@/components/layout/BottomNav';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import type { Document, DocumentListResponse, Summary } from '@/lib/api';
import { EXPENSE_CATEGORY_LIST } from '@/lib/categories';

vi.mock('@clerk/nextjs', () => ({
  useUser: () => ({ user: null, isLoaded: true, isSignedIn: false }),
  useClerk: () => ({ signOut: vi.fn() }),
}));

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      getDocuments: vi.fn(),
      getSummary: vi.fn(),
      downloadExport: vi.fn(),
      upsertVatSales: vi.fn(),
    },
  };
});

import { api } from '@/lib/api';
import ReceiptsPage from '@/app/receipts/page';
import SummaryPage from '@/app/summary/page';

function receipt(): Document {
  return {
    id: 'doc-first',
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

function list(documents: Document[], total = documents.length): DocumentListResponse {
  return { documents, total, page: 1, page_size: 50, has_more: false };
}

function emptySummary(overrides: Partial<Summary> = {}): Summary {
  return {
    period: '2026-Q4',
    period_type: 'quarter',
    year: 2026,
    period_value: 4,
    total_documents: 0,
    ready_count: 0,
    excluded_count: 0,
    excluded_documents: [],
    needs_review_count: 0,
    processing_count: 0,
    failed_count: 0,
    total_gross: '0.00',
    total_net: '0.00',
    total_vat: '0.00',
    deductible_vat: '0.00',
    deductible_vat_pending: '0.00',
    vat_on_sales: null,
    estimated_iva_payable: null,
    expense_breakdown: [],
    irs_breakdown: [],
    confidence_percent: 0,
    warnings: [],
    ...overrides,
  };
}

function renderInApp(page: React.ReactElement) {
  return render(<AuthProvider>{page}</AuthProvider>);
}

beforeEach(() => {
  localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ email: 'nova@example.com', id: 'ignored' }));
});

afterEach(() => {
  localStorage.removeItem(DEMO_AUTH_KEY);
  vi.clearAllMocks();
});

describe('IVA dashboard for an account with no documents', () => {
  beforeEach(() => {
    vi.mocked(api.getDocuments).mockResolvedValue(list([], 0));
    vi.mocked(api.getSummary).mockResolvedValue(emptySummary());
  });

  it('shows only the first-run prompt, with no deadline, ring or sales-VAT nag', async () => {
    const { container } = renderInApp(<SummaryPage />);

    const cta = await screen.findByRole('link', { name: 'Carregar recibo' });
    expect(cta).toHaveAttribute('href', '/upload');
    expect(screen.getByText('Ainda sem recibos')).toBeInTheDocument();

    expect(screen.queryByText(/Faltam \d+ dias/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Prazo de entrega/)).not.toBeInTheDocument();
    expect(screen.queryByText('Falta o IVA das vendas')).not.toBeInTheDocument();
    expect(screen.queryByText(/^\d+%$/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mês' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Trimestre' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Enviar ao Contabilista/ })).not.toBeInTheDocument();

    const icon = container.querySelector('main [data-icon="receipt-slip"]');
    expect(icon).not.toBeNull();
    expect(icon).toHaveClass('w-6', 'h-6', 'text-[var(--ff-accent)]');
    expect(container.querySelector('main .lucide-receipt')).toBeNull();
  });

  it('asks for the account-wide count, not the period count', async () => {
    renderInApp(<SummaryPage />);
    await screen.findByRole('link', { name: 'Carregar recibo' });
    expect(api.getDocuments).toHaveBeenCalledWith({ page_size: 1 });
  });

  it('falls back to the full dashboard when the count cannot be loaded', async () => {
    vi.mocked(api.getDocuments).mockRejectedValue(new Error('offline'));
    vi.spyOn(console, 'error').mockImplementation(() => {});
    renderInApp(<SummaryPage />);
    expect(await screen.findByText(/Prazo de entrega/)).toBeInTheDocument();
  });
});

describe('IVA dashboard once a document exists', () => {
  it('shows the widgets for an empty period, with a muted 0% ring at 12 px', async () => {
    vi.mocked(api.getDocuments).mockResolvedValue(list([receipt()], 1));
    vi.mocked(api.getSummary).mockResolvedValue(emptySummary());

    renderInApp(<SummaryPage />);

    expect(await screen.findByText(/Prazo de entrega/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Trimestre' })).toBeInTheDocument();
    expect(screen.getByText('Falta o IVA das vendas')).toBeInTheDocument();

    const ringLabel = screen.getAllByText('0%').find((el) => el.closest('.relative.w-12'))!;
    expect(ringLabel).toHaveClass('text-xs', 'text-[var(--ff-text-muted)]');
    expect(ringLabel.className).not.toMatch(/text-\[10px\]|text-red-/);
    const ring = ringLabel.parentElement!.querySelectorAll('circle')[1];
    expect(ring.getAttribute('stroke')).toBe('var(--ff-text-muted)');
  });

  it('keeps the warning colour for a low but non-zero share reviewed', async () => {
    vi.mocked(api.getDocuments).mockResolvedValue(list([receipt()], 4));
    vi.mocked(api.getSummary).mockResolvedValue(
      emptySummary({ total_documents: 4, ready_count: 1, confidence_percent: 25 }),
    );

    renderInApp(<SummaryPage />);

    const ringLabel = (await screen.findAllByText('25%')).find((el) => el.closest('.relative.w-12'))!;
    expect(ringLabel).toHaveClass('text-xs', 'text-red-500');
  });
});

describe('receipts list for an account with no documents', () => {
  it('renders no search, no date inputs and no category chips, only the prompt', async () => {
    vi.mocked(api.getDocuments).mockResolvedValue(list([]));
    const { container } = renderInApp(<ReceiptsPage />);

    const cta = await screen.findByRole('link', { name: 'Carregar recibo' });
    expect(cta).toHaveAttribute('href', '/upload');
    expect(screen.queryByLabelText('De')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Até')).not.toBeInTheDocument();
    expect(container.querySelectorAll('input[type="search"]')).toHaveLength(0);
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Todos' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Limpar filtros' })).not.toBeInTheDocument();

    expect(container.querySelector('main [data-icon="receipt-slip"]')).toHaveClass('w-6', 'h-6');
    expect(container.querySelector('main .lucide-receipt')).toBeNull();
  });

  it('hides the filters while the first load is in flight', () => {
    vi.mocked(api.getDocuments).mockReturnValue(new Promise(() => {}));
    const { container } = renderInApp(<ReceiptsPage />);
    expect(screen.queryByLabelText('De')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Até')).not.toBeInTheDocument();
    expect(container.querySelectorAll('input[type="search"]')).toHaveLength(0);
  });
});

describe('receipts list once a document exists', () => {
  it('shows search, both date inputs and the category chips', async () => {
    vi.mocked(api.getDocuments).mockResolvedValue(list([receipt()]));
    renderInApp(<ReceiptsPage />);

    expect(await screen.findByRole('button', { name: 'Todos' })).toBeInTheDocument();
    expect(screen.getByLabelText('De')).toHaveAttribute('placeholder', 'dd/mm/aaaa');
    expect(screen.getByLabelText('Até')).toHaveAttribute('placeholder', 'dd/mm/aaaa');
    expect(screen.getByRole('searchbox', { name: 'Procurar recibos' })).toBeInTheDocument();
  });

  it('keeps the filters and offers "Limpar filtros" when a filter matches nothing', async () => {
    vi.mocked(api.getDocuments).mockResolvedValue(list([receipt()]));
    renderInApp(<ReceiptsPage />);

    vi.mocked(api.getDocuments).mockResolvedValue(list([]));
    fireEvent.click(await screen.findByRole('button', { name: EXPENSE_CATEGORY_LIST[0].label }));

    expect(await screen.findByRole('button', { name: 'Limpar filtros' })).toBeInTheDocument();
    expect(screen.getByLabelText('De')).toBeInTheDocument();
    expect(screen.getByLabelText('Até')).toBeInTheDocument();
    expect(screen.getByRole('searchbox')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Carregar recibo' })).not.toBeInTheDocument();
  });

  it('keeps the inputs mounted after clearing a filter that matched nothing', async () => {
    vi.mocked(api.getDocuments).mockResolvedValue(list([receipt()]));
    renderInApp(<ReceiptsPage />);

    vi.mocked(api.getDocuments).mockResolvedValue(list([]));
    const from = await screen.findByLabelText('De');
    fireEvent.change(from, { target: { value: '01/01/2030' } });
    fireEvent.blur(from);
    await screen.findByRole('button', { name: 'Limpar filtros' });

    vi.mocked(api.getDocuments).mockReturnValue(new Promise(() => {}));
    fireEvent.change(screen.getByLabelText('De'), { target: { value: '' } });
    fireEvent.blur(screen.getByLabelText('De'));
    await waitFor(() => expect(api.getDocuments).toHaveBeenCalledTimes(3));
    expect(screen.getByLabelText('De')).toBeInTheDocument();
  });
});

describe('bottom navigation', () => {
  it('uses the slip icon for Recibos, with no dollar receipt glyph', () => {
    const { container } = render(<BottomNav />);
    const link = screen.getByRole('link', { name: 'Recibos' });
    expect(link.querySelector('[data-icon="receipt-slip"]')).not.toBeNull();
    expect(container.querySelector('.lucide-receipt')).toBeNull();
  });
});
