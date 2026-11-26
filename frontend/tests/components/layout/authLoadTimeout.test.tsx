import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  AUTH_LOAD_FAILED,
  AUTH_LOAD_FAILED_HINT,
  AUTH_LOAD_TIMEOUT_MS,
  AppLayout,
} from '@/components/layout/AppLayout';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { reloadPage } from '@/lib/navigate';

// clerk-js state, changed by the tests: blocked/offline clerk-js never sets isLoaded.
const clerk = vi.hoisted(() => ({ isLoaded: false, isSignedIn: false }));

vi.mock('@clerk/nextjs', () => ({
  useUser: () => ({
    isLoaded: clerk.isLoaded,
    isSignedIn: clerk.isSignedIn,
    user: clerk.isSignedIn ? { id: 'user_1', fullName: 'Ana', primaryEmailAddress: { emailAddress: 'ana@empresa.pt' } } : null,
  }),
  useClerk: () => ({ signOut: vi.fn() }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/receipts',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/navigate', () => ({ reloadPage: vi.fn(), hardNavigate: vi.fn() }));

function page() {
  return (
    <AuthProvider>
      <AppLayout title="Recibos">
        <p>Lista de recibos</p>
      </AppLayout>
    </AuthProvider>
  );
}

describe('protected page while clerk-js loads', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubEnv('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY', 'pk_test_x');
    clerk.isLoaded = false;
    clerk.isSignedIn = false;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    vi.mocked(reloadPage).mockReset();
  });

  it('shows the spinner, then a calm error with a reload button if clerk-js never loads', () => {
    render(page());
    expect(screen.getByText('A carregar…')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    // Not before Clerk's own getToken wait (10 s) is over…
    act(() => vi.advanceTimersByTime(10_000));
    expect(screen.getByText('A carregar…')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    // …and no later than 15 s.
    act(() => vi.advanceTimersByTime(AUTH_LOAD_TIMEOUT_MS - 10_000 - 1));
    expect(AUTH_LOAD_TIMEOUT_MS).toBeLessThanOrEqual(15_000);
    expect(screen.getByText('A carregar…')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByText('A carregar…')).not.toBeInTheDocument();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent(AUTH_LOAD_FAILED);
    expect(alert).toHaveTextContent(AUTH_LOAD_FAILED_HINT);
    expect(alert.outerHTML).not.toMatch(/red-|danger/);
    // The button sits outside the alert, so only the message is announced.
    const retry = screen.getByRole('button', { name: 'Tentar de novo' });
    expect(alert).not.toContainElement(retry);

    fireEvent.click(retry);
    expect(reloadPage).toHaveBeenCalledTimes(1);
  });

  it('never shows the error when clerk-js loads in time', () => {
    const { rerender } = render(page());
    act(() => vi.advanceTimersByTime(5_000));
    clerk.isLoaded = true;
    clerk.isSignedIn = true;
    rerender(page());
    expect(screen.getByText('Lista de recibos')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(AUTH_LOAD_TIMEOUT_MS * 2));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('Lista de recibos')).toBeInTheDocument();
  });

  it('shows the page if clerk-js arrives after the error', () => {
    const { rerender } = render(page());
    act(() => vi.advanceTimersByTime(AUTH_LOAD_TIMEOUT_MS));
    expect(screen.getByRole('alert')).toHaveTextContent(AUTH_LOAD_FAILED);

    clerk.isLoaded = true;
    clerk.isSignedIn = true;
    rerender(page());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('Lista de recibos')).toBeInTheDocument();
  });
});
