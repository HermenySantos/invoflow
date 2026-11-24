import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppLayout } from '@/components/layout/AppLayout';
import { AuthProvider, useAuth } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import { readScroll, scrollKey, writeScroll } from '@/lib/mainScroll';

vi.mock('@clerk/nextjs', () => ({
  useUser: () => ({ user: null, isLoaded: true, isSignedIn: false }),
  useClerk: () => ({ signOut: vi.fn() }),
}));

describe('AppLayout on a phone', () => {
  afterEach(() => {
    localStorage.removeItem(DEMO_AUTH_KEY);
  });

  it('scrolls only the content area, so no control can sit under the bottom nav', async () => {
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'demo', email: 'ana@empresa.pt' }));
    render(
      <AuthProvider>
        <AppLayout title="IVA">
          <button type="button">Editar IVA vendas</button>
        </AppLayout>
      </AuthProvider>,
    );

    const nav = (await screen.findAllByRole('navigation', { name: 'Navegação principal' }))
      .find((el) => el.className.includes('border-t'))!;
    const main = screen.getByRole('main');
    const pane = main.parentElement!;
    const shell = pane.parentElement!;

    // A fixed nav over a scrolling page hid whatever control was at the fold (360x800).
    expect(nav.className).not.toMatch(/\b(fixed|absolute|sticky)\b/);
    expect(nav.className).toContain('shrink-0');
    expect(shell.className).toContain('h-[100dvh]');
    expect(shell.className).toContain('flex-col');
    expect(pane.className).toContain('flex-1');
    expect(pane.className).toContain('min-h-0');
    expect(pane.className).toContain('flex-col');
    expect(main.className).toContain('flex-1');
    expect(main.className).toContain('min-h-0');
    expect(main.className).toContain('overflow-y-auto');
    expect(pane.nextElementSibling).toBe(nav);
    expect(main).toContainElement(screen.getByRole('button', { name: 'Editar IVA vendas' }));
    expect(main.firstElementChild).toHaveClass('pb-4');
  });

  it('prints the whole page: no scroll area clipping, no nav', async () => {
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'demo', email: 'ana@empresa.pt' }));
    render(
      <AuthProvider>
        <AppLayout title="Recibos">
          <p>Lista</p>
        </AppLayout>
      </AuthProvider>,
    );

    const nav = (await screen.findAllByRole('navigation', { name: 'Navegação principal' }))
      .find((el) => el.className.includes('border-t'))!;
    const main = screen.getByRole('main');
    expect(main).toHaveAttribute('id', 'main-content');
    expect(main).toHaveClass('print:overflow-visible', 'print:h-auto');
    expect(main.parentElement?.parentElement).toHaveClass('print:block', 'print:h-auto');
    expect(nav).toHaveClass('print:hidden');
  });

  it('puts a 44×44 account link to /settings in the header, with the user initial, and no Sair button', async () => {
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'demo', email: 'ana@empresa.pt' }));
    render(
      <AuthProvider>
        <AppLayout title="Recibos">
          <p>Lista</p>
        </AppLayout>
      </AuthProvider>,
    );

    const account = within(await screen.findByRole('banner')).getByRole('link', { name: 'Conta' });
    expect(account).toHaveAttribute('href', '/settings');
    expect(account).toHaveClass('hidden', 'h-11', 'w-11');
    expect(account).toHaveTextContent('A');
    expect(account).not.toHaveAttribute('aria-current');
    expect(screen.queryByRole('button', { name: 'Sair' })).not.toBeInTheDocument();
  });

  it('forgets every saved scroll position on sign-out', async () => {
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'demo', email: 'ana@empresa.pt' }));
    writeScroll('/receipts', 1200);
    writeScroll('/receipts?status=ready', 300);
    sessionStorage.setItem('other', 'kept');
    function SignOutButton() {
      const { signOut } = useAuth();
      return <button type="button" onClick={() => signOut()}>Terminar</button>;
    }
    render(
      <AuthProvider>
        <AppLayout title="Recibos">
          <SignOutButton />
        </AppLayout>
      </AuthProvider>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Terminar' }));
    expect(readScroll('/receipts')).toBe(0);
    expect(sessionStorage.getItem(scrollKey('/receipts?status=ready'))).toBeNull();
    expect(sessionStorage.getItem('other')).toBe('kept');
    sessionStorage.removeItem('other');
  });
});
