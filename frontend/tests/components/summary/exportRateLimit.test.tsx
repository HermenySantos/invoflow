import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SummaryPage from '@/app/summary/page';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import { api, Summary } from '@/lib/api';
import { expectEmptyRegion, expectRegionSays, getRateLimitRegion } from '../../rateLimitRegion';

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
    ready_count: 2,
    needs_review_count: 0,
    processing_count: 0,
    failed_count: 0,
    total_gross: '24.60',
    total_net: '20.00',
    total_vat: '4.60',
    deductible_vat: '4.60',
    deductible_vat_pending: '0.00',
    vat_on_sales: null,
    estimated_iva_payable: null,
    expense_breakdown: [],
    irs_breakdown: [],
    confidence_percent: 90,
    warnings: [],
  };
}

const RETRY_AFTER = 42;

describe('summary export when rate limited (429)', () => {
  let regionBefore: HTMLElement;

  beforeEach(async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'demo', email: 'ana@empresa.pt' }));
    vi.mocked(api.getDocuments).mockResolvedValue({ documents: [], total: 2, page: 1, page_size: 1, has_more: true });
    vi.mocked(api.getSummary).mockResolvedValue(summary());
    vi.mocked(api.downloadExport)
      .mockRejectedValueOnce({
        status: 429,
        message: 'Demasiados pedidos. Aguarde 40 s e tente novamente.',
        retryAfter: RETRY_AFTER,
      })
      .mockResolvedValueOnce({ blob: new Blob(['zip']), filename: 'Invoflow_T1_2026.zip' });
    render(
      <AuthProvider>
        <SummaryPage />
      </AuthProvider>,
    );
    const exportButton = await screen.findByRole('button', { name: 'Enviar ao Contabilista' });
    // ARIA22 step 1: the status region is already there, empty, before any 429.
    regionBefore = getRateLimitRegion();
    expectEmptyRegion(regionBefore);
    fireEvent.click(exportButton);
  });

  afterEach(() => {
    vi.useRealTimers();
    localStorage.removeItem(DEMO_AUTH_KEY);
    vi.resetAllMocks();
  });

  it('says how many seconds to wait, in a calm status, with no bare "Tente novamente"', async () => {
    const notice = await screen.findByTestId('rate-limit-notice');
    // ARIA22 step 2: the message lands in the same, already-mounted region.
    const region = getRateLimitRegion();
    expect(region).toBe(regionBefore);
    expect(region).toContainElement(notice);
    expectRegionSays(region, `Aguarde um momento. Pode tentar de novo dentro de ${RETRY_AFTER} s.`);
    expect(notice).toHaveTextContent(`Aguarde um momento. Pode tentar de novo dentro de ${RETRY_AFTER} s.`);
    expect(notice.textContent).not.toMatch(/Tente (novamente|outra vez)/i);
    expect(notice.outerHTML).not.toMatch(/red-|danger/);
    expect(screen.queryByText('Exportação falhou. Tente novamente.')).not.toBeInTheDocument();
  });

  it('disables the export button and counts down outside any live region, then re-enables it at 0', async () => {
    const notice = await screen.findByTestId('rate-limit-notice');
    const button = screen.getByRole('button', { name: `Tentar de novo em ${RETRY_AFTER} s` });
    expect(button).toBeDisabled();
    expect(button.closest('[aria-live],[role="status"],[role="alert"]')).toBeNull();

    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByRole('button', { name: `Tentar de novo em ${RETRY_AFTER - 1} s` })).toBeDisabled();
    // The status node is inserted once and its text does not tick, so it is announced once.
    expect(screen.getByTestId('rate-limit-notice')).toBe(notice);
    expect(notice).toHaveTextContent(`dentro de ${RETRY_AFTER} s`);

    act(() => vi.advanceTimersByTime((RETRY_AFTER - 1) * 1000));
    const again = screen.getByRole('button', { name: 'Enviar ao Contabilista' });
    expect(again).toBeEnabled();
    expect(screen.queryByTestId('rate-limit-notice')).not.toBeInTheDocument();
    // The region stays mounted and empties, so nothing new is announced when the wait ends.
    expect(getRateLimitRegion()).toBe(regionBefore);
    expectEmptyRegion(regionBefore);

    fireEvent.click(again);
    await waitFor(() => expect(api.downloadExport).toHaveBeenCalledTimes(2));
    expect(URL.createObjectURL).toHaveBeenCalled();
  });
});
