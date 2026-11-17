import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppLayout } from '@/components/layout/AppLayout';
import { AuthProvider } from '@/components/providers/AuthProvider';
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

    const nav = await screen.findByRole('navigation', { name: 'Navegação principal' });
    const main = screen.getByRole('main');
    const shell = main.parentElement!;

    // A fixed nav over a scrolling page hid whatever control was at the fold (360x800).
    expect(nav.className).not.toMatch(/\b(fixed|absolute|sticky)\b/);
    expect(nav.className).toContain('shrink-0');
    expect(shell.className).toContain('h-[100dvh]');
    expect(shell.className).toContain('flex-col');
    expect(main.className).toContain('flex-1');
    expect(main.className).toContain('min-h-0');
    expect(main.className).toContain('overflow-y-auto');
    expect(main.nextElementSibling).toBe(nav);
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

    const nav = await screen.findByRole('navigation', { name: 'Navegação principal' });
    const main = screen.getByRole('main');
    expect(main).toHaveAttribute('id', 'main-content');
    expect(main).toHaveClass('print:overflow-visible', 'print:h-auto');
    expect(main.parentElement).toHaveClass('print:block', 'print:h-auto');
    expect(nav).toHaveClass('print:hidden');
  });

  it('forgets every saved scroll position on sign-out (Sair)', async () => {
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'demo', email: 'ana@empresa.pt' }));
    writeScroll('/receipts', 1200);
    writeScroll('/receipts?status=ready', 300);
    sessionStorage.setItem('other', 'kept');
    render(
      <AuthProvider>
        <AppLayout title="Recibos">
          <p>Lista</p>
        </AppLayout>
      </AuthProvider>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Sair' }));
    expect(readScroll('/receipts')).toBe(0);
    expect(sessionStorage.getItem(scrollKey('/receipts?status=ready'))).toBeNull();
    expect(sessionStorage.getItem('other')).toBe('kept');
    sessionStorage.removeItem('other');
  });
});
