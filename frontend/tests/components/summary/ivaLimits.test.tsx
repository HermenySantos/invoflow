import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SummaryPage from '@/app/summary/page';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY, isDemoMode } from '@/lib/demoUser';
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
      downloadExport: vi.fn(),
      upsertVatSales: vi.fn(),
    },
  };
});

function memoryStorage(): Storage {
  const items = new Map<string, string>();
  return {
    get length() { return items.size; },
    clear: () => items.clear(),
    getItem: (key) => items.get(key) ?? null,
    key: (index) => Array.from(items.keys())[index] ?? null,
    removeItem: (key) => { items.delete(key); },
    setItem: (key, value) => { items.set(key, String(value)); },
  };
}

function summary(overrides: Partial<Summary> = {}): Summary {
  return {
    period: '2026-Q4',
    period_type: 'quarter',
    year: 2026,
    period_value: 4,
    total_documents: 1,
    ready_count: 1,
    needs_review_count: 0,
    processing_count: 0,
    failed_count: 0,
    total_gross: '48.60',
    total_net: '39.51',
    total_vat: '9.09',
    deductible_vat: '9.09',
    deductible_vat_pending: '0.00',
    vat_on_sales: null,
    estimated_iva_payable: null,
    expense_breakdown: [],
    irs_breakdown: [],
    confidence_percent: 100,
    warnings: [],
    ...overrides,
  };
}

describe('summary IVA limits', () => {
  beforeEach(() => {
    const storage = memoryStorage();
    storage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'demo', email: 'ana@empresa.pt' }));
    vi.stubGlobal('localStorage', storage);
    vi.mocked(api.getSummary).mockResolvedValue(summary());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('says the figure ignores VAT on sales until that amount is entered', async () => {
    render(
      <AuthProvider>
        <SummaryPage />
      </AuthProvider>,
    );

    expect(await screen.findByText('Estimativa. Este valor ignora o IVA das vendas.')).toBeInTheDocument();
    expect(screen.getByText(/Prazo de entrega/)).toBeInTheDocument();
    expect(screen.queryByText(/Prazo de pagamento/)).not.toBeInTheDocument();
    if (isDemoMode) {
      expect(screen.getByText(/armazenamento de ficheiros são simulados/)).toBeInTheDocument();
    }
  });

  it('does not claim a figure that includes typed sales VAT ignores it', async () => {
    vi.mocked(api.getSummary).mockResolvedValue(
      summary({ vat_on_sales: '100.00', estimated_iva_payable: '90.91' }),
    );

    render(
      <AuthProvider>
        <SummaryPage />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/introduziu à mão/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/ignora o IVA das vendas/)).not.toBeInTheDocument();
  });

  it('lists receipts excluded from the IVA totals', async () => {
    vi.mocked(api.getSummary).mockResolvedValue(
      summary({
        ready_count: 0,
        excluded_count: 1,
        excluded_documents: [
          {
            id: 'doc-1',
            vendor_name: 'Ana Exemplo',
            invoice_number: 'FT A/12',
            document_type: 'unclassified',
            status: 'needs_review',
            reason: 'por classificar',
          },
        ],
      }),
    );

    render(
      <AuthProvider>
        <SummaryPage />
      </AuthProvider>,
    );

    expect(await screen.findByText(/Excluídos do IVA \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Ana Exemplo/)).toBeInTheDocument();
    expect(screen.getByText(/por classificar/)).toBeInTheDocument();
  });
});
