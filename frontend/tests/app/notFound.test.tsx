import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import NotFound from '@/app/not-found';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';

vi.mock('@clerk/nextjs', () => ({
  useUser: () => ({ user: null, isLoaded: true, isSignedIn: false }),
  useClerk: () => ({ signOut: vi.fn() }),
}));

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

function renderNotFound() {
  return render(
    <AuthProvider>
      <NotFound />
    </AuthProvider>,
  );
}

const ENGLISH = /\b(not found|page|could not|go (back|home)|home|return|sorry|error|upload|sign in|receipts?)\b/i;

describe('404 recovery page', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', memoryStorage());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the approved PT-PT copy and no English UI strings', () => {
    const { container } = renderNotFound();

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Esta página não existe');
    expect(
      screen.getByText('O endereço pode estar errado, ou a página já não está disponível.'),
    ).toBeInTheDocument();
    expect(screen.getByText('404')).toBeInTheDocument();
    expect(container.textContent).not.toMatch(ENGLISH);
  });

  it('sends a signed-out visitor to sign-in with next=/receipts', async () => {
    renderNotFound();

    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'Ir para os recibos' })).toHaveAttribute(
        'href',
        '/sign-in?next=/receipts',
      ),
    );
    expect(screen.getByRole('link', { name: 'Carregar um recibo' })).toHaveAttribute('href', '/upload');
  });

  it('sends a demo-session visitor straight to /receipts', async () => {
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'x', email: 'demo@invoflow.test' }));
    renderNotFound();

    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'Ir para os recibos' })).toHaveAttribute('href', '/receipts'),
    );
  });

  it('keeps both CTAs at a 44×44 tap target at every width', () => {
    renderNotFound();

    for (const name of ['Ir para os recibos', 'Carregar um recibo']) {
      const classes = screen.getByRole('link', { name }).className.split(/\s+/);
      expect(classes).toContain('min-h-11');
      expect(classes).toContain('min-w-11');
      expect(classes).not.toContain('lg:min-h-0');
    }
    expect(screen.getByRole('link', { name: 'Ir para os recibos' }).className).toContain('lg:min-h-11');
  });
});
