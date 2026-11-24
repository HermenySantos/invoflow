import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppLayout } from '@/components/layout/AppLayout';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';

const pathname = vi.hoisted(() => ({ current: '/upload' }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => pathname.current,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@clerk/nextjs', () => ({
  useUser: () => ({ user: null, isLoaded: true, isSignedIn: false }),
  useClerk: () => ({ signOut: vi.fn() }),
}));

function renderShell() {
  localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'demo', email: 'ana@empresa.pt' }));
  return render(
    <AuthProvider>
      <AppLayout title="Recibos">
        <p>Lista</p>
      </AppLayout>
    </AuthProvider>,
  );
}

function railNav() {
  const nav = screen.getAllByRole('navigation', { name: 'Navegação principal' })
    .find((el) => el.className.includes('w-[220px]'));
  expect(nav, 'desktop rail').toBeTruthy();
  return nav!;
}

function bottomNav() {
  const nav = screen.getAllByRole('navigation', { name: 'Navegação principal' })
    .find((el) => el.className.includes('border-t'));
  expect(nav, 'bottom nav').toBeTruthy();
  return nav!;
}

describe('desktop left rail', () => {
  it('highlights Carregar on /scan and /upload, in the rail and the bottom nav', async () => {
    pathname.current = '/scan';
    renderShell();

    const carregar = await screen.findAllByRole('link', { name: 'Carregar' });
    expect(carregar.map((link) => link.getAttribute('href'))).toEqual(['/upload', '/upload']);
    for (const link of carregar) {
      expect(link).toHaveAttribute('aria-current', 'page');
    }
    expect(screen.getAllByRole('link', { name: 'Recibos' }).every((link) => !link.hasAttribute('aria-current'))).toBe(true);
  });

  it('highlights Carregar on /upload the same way', async () => {
    pathname.current = '/upload';
    renderShell();
    const carregar = await screen.findAllByRole('link', { name: 'Carregar' });
    expect(carregar).toHaveLength(2);
    for (const link of carregar) {
      expect(link).toHaveAttribute('href', '/upload');
      expect(link).toHaveAttribute('aria-current', 'page');
    }
  });

  it('marks the header Conta link, the one shown below 1024, as the current page on /settings', async () => {
    pathname.current = '/settings';
    renderShell();

    const headerAccount = (await screen.findByRole('banner')).querySelector('a') as HTMLAnchorElement;
    expect(headerAccount).toHaveAttribute('href', '/settings');
    expect(headerAccount).toHaveAttribute('aria-current', 'page');
    expect(headerAccount).toHaveClass('lg:hidden');
    expect(headerAccount).toHaveAccessibleName('Conta');

    const bottomAccount = within(bottomNav()).getByRole('link', { name: 'Conta' });
    expect(bottomAccount).toHaveAttribute('href', '/settings');
    expect(bottomAccount).toHaveAttribute('aria-current', 'page');
  });

  it('hides the bottom nav from 1024px up and the rail below that, so only one nav is shown', async () => {
    pathname.current = '/receipts';
    renderShell();

    const bottom = bottomNav();
    const rail = railNav();
    expect(bottom).toHaveClass('lg:hidden');
    expect(rail).toHaveClass('hidden', 'lg:flex');
    expect(rail.className).not.toMatch(/(?:^|\s)lg:hidden(?:\s|$)/);
  });

  it('lists Invoflow, Carregar, Recibos, IVA and Conta, with no Sair', async () => {
    pathname.current = '/receipts/doc-1';
    renderShell();

    const rail = railNav();
    expect(rail).toHaveTextContent('Invoflow');
    const links = Array.from(rail.querySelectorAll('a')).map((link) => ({
      label: link.textContent?.replace(/\s+/g, '') ?? '',
      href: link.getAttribute('href'),
      current: link.getAttribute('aria-current'),
    }));
    expect(links).toEqual([
      { label: 'Carregar', href: '/upload', current: null },
      { label: 'Recibos', href: '/receipts', current: 'page' },
      { label: 'IVA', href: '/summary', current: null },
      { label: 'Conta', href: '/settings', current: null },
    ]);
    expect(rail).not.toHaveTextContent('Sair');
    expect(screen.queryByRole('button', { name: 'Sair' })).not.toBeInTheDocument();
  });

  it('styles the active item with a 3px accent bar and keeps every item at least 44px tall', async () => {
    pathname.current = '/summary';
    renderShell();

    const rail = railNav();
    const active = rail.querySelector('a[aria-current="page"]') as HTMLAnchorElement;
    const idle = Array.from(rail.querySelectorAll('a')).find((link) => link.getAttribute('href') === '/upload')!;

    expect(active).toHaveClass('min-h-11', 'font-semibold', 'border-l-[3px]', 'border-l-[#1b4d3e]');
    expect(active.className).toMatch(/bg-\[#1b4d3e\]\/\[0\.08\]|bg-\[#1b4d3e\]\/8/);
    expect(idle).toHaveClass('min-h-11', 'font-normal', 'text-[#5c5c5c]');
    expect(idle).not.toHaveClass('font-semibold');

    const wordmark = within(rail).getByText('Invoflow');
    expect(wordmark).toHaveClass('font-sans', 'font-semibold', 'text-[18px]');
    expect(rail).toHaveClass('bg-white', 'border-r', 'border-[#e5e5e0]', 'sticky', 'w-[220px]');
    expect(rail.querySelector('a')!.className).not.toMatch(/color-mix|\/25|25%/);
    expect(rail.innerHTML).not.toContain('Fraunces');
  });

  it('uses the full accent focus ring, not a 25% mix', async () => {
    pathname.current = '/upload';
    renderShell();

    const link = railNav().querySelector('a')!;
    expect(link.className).toContain('focus-visible:ring-2');
    expect(link.className).toContain('focus-visible:ring-[var(--ff-accent)]');
    expect(link.className).toContain('focus-visible:ring-offset-2');
    expect(link.className).not.toMatch(/color-mix|ring-primary/);
  });

  it('tabs skip link, then the rail, then main, and widens the column at md and lg', async () => {
    pathname.current = '/receipts';
    renderShell();

    const skip = screen.getByRole('link', { name: 'Saltar para o conteúdo' });
    const rail = railNav();
    const main = screen.getByRole('main');
    const bottom = bottomNav();

    expect(skip.compareDocumentPosition(rail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(rail.compareDocumentPosition(main) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(main.compareDocumentPosition(bottom) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    const headerAccount = screen.getByRole('banner').querySelector('a')!;
    expect(headerAccount).toHaveClass('lg:hidden');

    const column = main.firstElementChild as HTMLElement;
    expect(column).toHaveClass('max-w-lg', 'md:max-w-3xl', 'md:px-8', 'lg:max-w-4xl', 'lg:mx-0');
    const headerColumn = screen.getByRole('banner').firstElementChild as HTMLElement;
    expect(headerColumn).toHaveClass('max-w-lg', 'md:max-w-3xl', 'md:px-8', 'lg:max-w-4xl', 'lg:mx-0');
  });
});
