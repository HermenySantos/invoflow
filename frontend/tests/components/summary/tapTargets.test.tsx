import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SummaryPage from '@/app/summary/page';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import { api, Summary } from '@/lib/api';

vi.mock('@clerk/nextjs', () => ({
  useUser: () => ({ user: null, isLoaded: true, isSignedIn: false }),
  useClerk: () => ({ signOut: vi.fn() }),
}));

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      getSummary: vi.fn(),
      getDocuments: vi.fn(),
      downloadExport: vi.fn(),
      upsertVatSales: vi.fn(),
    },
  };
});

function summary(): Summary {
  return {
    period: '2026-Q1',
    period_type: 'quarter',
    year: 2026,
    period_value: 1,
    total_documents: 2,
    ready_count: 1,
    excluded_count: 1,
    excluded_documents: [
      { id: 'doc-1', vendor_name: 'Oficina do Bairro', invoice_number: 'FT A/1', document_type: null, status: 'needs_review', reason: 'Por rever' },
    ],
    needs_review_count: 1,
    processing_count: 0,
    failed_count: 0,
    total_gross: '24.60',
    total_net: '20.00',
    total_vat: '4.60',
    deductible_vat: '2.30',
    deductible_vat_pending: '2.30',
    vat_on_sales: null,
    estimated_iva_payable: null,
    expense_breakdown: [],
    irs_breakdown: [],
    confidence_percent: 90,
    warnings: [],
  };
}

/** 44 px below lg; from lg up the min-height (and min-width) is dropped, so the desktop size is unchanged. */
function expectMobileHeight(element: HTMLElement) {
  expect(element).toHaveClass('min-h-11', 'lg:min-h-0');
}

function expectMobileSquare(element: HTMLElement) {
  expect(element).toHaveClass('min-h-11', 'min-w-11', 'lg:min-h-0', 'lg:min-w-0');
}

describe('summary tap targets on a phone', () => {
  beforeEach(async () => {
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'demo', email: 'ana@empresa.pt' }));
    vi.mocked(api.getDocuments).mockResolvedValue({ documents: [], total: 2, page: 1, page_size: 1, has_more: true });
    vi.mocked(api.getSummary).mockResolvedValue(summary());
    render(
      <AuthProvider>
        <SummaryPage />
      </AuthProvider>,
    );
    await screen.findByText('Falta o IVA das vendas');
  });

  afterEach(() => {
    localStorage.removeItem(DEMO_AUTH_KEY);
    vi.clearAllMocks();
  });

  it('gives the Mês / Trimestre toggle 44 px', () => {
    expectMobileHeight(screen.getByRole('button', { name: 'Mês' }));
    expectMobileHeight(screen.getByRole('button', { name: 'Trimestre' }));
  });

  it('gives the period arrows 44 × 44 px', () => {
    expectMobileSquare(screen.getByRole('button', { name: 'Período anterior' }));
    expectMobileSquare(screen.getByRole('button', { name: 'Próximo período' }));
  });

  it("gives 'Introduzir IVA das vendas', the pencil and the excluded receipt link 44 px", () => {
    expectMobileHeight(screen.getByRole('button', { name: 'Introduzir IVA das vendas' }));
    expectMobileSquare(screen.getByRole('button', { name: 'Editar IVA vendas' }));
    const excluded = screen.getByRole('link', { name: 'Oficina do Bairro · FT A/1' });
    expectMobileHeight(excluded);
    expect(excluded).toHaveClass('break-words', 'min-w-0');
    expect(excluded.querySelector('span')).toHaveClass('break-words', 'min-w-0');
  });

  it('gives the VAT on sales input and its save and cancel buttons 44 px', () => {
    fireEvent.click(screen.getByRole('button', { name: 'Introduzir IVA das vendas' }));
    expectMobileHeight(screen.getByPlaceholderText('0,00'));
    expectMobileSquare(screen.getByRole('button', { name: 'Guardar' }));
    expectMobileSquare(screen.getByRole('button', { name: 'Cancelar' }));
  });
});
