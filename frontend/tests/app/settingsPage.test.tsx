import { readFileSync } from 'node:fs';
import path from 'node:path';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SettingsPage from '@/app/settings/page';
import { DeleteAccountSheet, isDeleteConfirmed } from '@/components/settings/DeleteAccountSheet';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY } from '@/lib/demoUser';
import { hardNavigate } from '@/lib/navigate';

const replace = vi.fn();
const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => '/settings',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@clerk/nextjs', () => ({
  useUser: () => ({ user: null, isLoaded: true, isSignedIn: false }),
  useClerk: () => ({ signOut: vi.fn() }),
}));

vi.mock('@/lib/navigate', () => ({ hardNavigate: vi.fn() }));

const signInDemo = () =>
  localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'demo-ana', email: 'ana@empresa.pt' }));

const renderSettings = () =>
  render(
    <AuthProvider>
      <SettingsPage />
    </AuthProvider>,
  );

describe('/settings', () => {
  beforeEach(() => {
    replace.mockClear();
    push.mockClear();
    vi.mocked(hardNavigate).mockClear();
  });

  afterEach(() => {
    localStorage.removeItem(DEMO_AUTH_KEY);
    vi.unstubAllEnvs();
  });

  it('shows the Conta eyebrow, the Definições title and the read-only email, without an empty name row', async () => {
    signInDemo();
    renderSettings();

    expect(await screen.findByRole('heading', { level: 1, name: 'Definições' })).toBeInTheDocument();
    expect(screen.getByText('Conta', { selector: 'header p' })).toBeInTheDocument();
    expect(screen.getByText('Email')).toBeInTheDocument();
    expect(screen.getByText('ana@empresa.pt')).toBeInTheDocument();
    expect(screen.queryByText('Nome')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Zona de perigo' })).toHaveClass('text-sm', 'font-semibold');
  });

  it('links bottom-nav Conta to /settings, with no header avatar link and no Sair button', async () => {
    signInDemo();
    renderSettings();

    expect(within(await screen.findByRole('banner')).queryByRole('link', { name: 'Conta' })).not.toBeInTheDocument();
    const account = screen.getAllByRole('link', { name: 'Conta' }).find((link) => link.closest('nav')?.className.includes('border-t'));
    expect(account).toHaveAttribute('href', '/settings');
    expect(account).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('button', { name: 'Sair' })).not.toBeInTheDocument();
  });

  it('asks before signing out, and on Terminar clears the session and goes to /', async () => {
    signInDemo();
    renderSettings();

    const trigger = await screen.findByRole('button', { name: 'Terminar sessão' });
    expect(trigger).toHaveClass('min-h-11');
    fireEvent.click(trigger);

    const dialog = screen.getByRole('alertdialog', { name: 'Terminar sessão?' });
    expect(dialog).toHaveAccessibleDescription('Vai sair desta conta neste dispositivo.');
    const terminar = screen.getByRole('button', { name: 'Terminar' });
    expect(terminar).toHaveClass('btn-accent-outline');
    expect(terminar).not.toHaveClass('btn-danger');

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(localStorage.getItem(DEMO_AUTH_KEY)).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Terminar sessão' }));
    fireEvent.click(screen.getByRole('button', { name: 'Terminar' }));
    expect(localStorage.getItem(DEMO_AUTH_KEY)).toBeNull();
    expect(hardNavigate).toHaveBeenCalledWith('/');
  });

  it('keeps the export disabled with “Disponível em breve” when NEXT_PUBLIC_ACCOUNT_EXPORT=0', async () => {
    vi.stubEnv('NEXT_PUBLIC_ACCOUNT_EXPORT', '0');
    signInDemo();
    renderSettings();

    const exportButton = await screen.findByRole('button', { name: 'Exportar os meus dados' });
    expect(exportButton).toBeDisabled();
    expect(exportButton).toHaveAccessibleDescription('Disponível em breve');
    fireEvent.click(exportButton);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('stops account deletion at step 1 with the placeholder body, since no delete API exists', async () => {
    vi.stubEnv('NEXT_PUBLIC_ACCOUNT_DELETE', '1');
    signInDemo();
    renderSettings();

    const trigger = await screen.findByRole('button', { name: 'Eliminar conta' });
    expect(trigger).toHaveClass('btn-ghost-danger', 'min-h-11');
    fireEvent.click(trigger);

    const dialog = screen.getByRole('alertdialog', { name: 'Eliminar a conta?' });
    expect(dialog).toHaveAccessibleDescription('[O que acontece aos recibos após eliminar a conta — a confirmar]');
    const continuar = screen.getByRole('button', { name: 'Continuar' });
    expect(continuar).toBeDisabled();
    expect(continuar).toHaveAccessibleDescription('A eliminação de conta ainda não está disponível.');
    expect(screen.queryByLabelText('Escreva ELIMINAR para confirmar')).not.toBeInTheDocument();
  });

  it('sends a signed-out visitor to /sign-in?next=/settings', async () => {
    renderSettings();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/sign-in?next=%2Fsettings'));
    expect(screen.queryByText('Definições')).not.toBeInTheDocument();
  });

  it('names every control and keeps the danger and accent tokens readable', async () => {
    signInDemo();
    renderSettings();
    await screen.findByRole('heading', { level: 1, name: 'Definições' });

    for (const control of [...screen.getAllByRole('button'), ...screen.getAllByRole('link')]) {
      expect(control).toHaveAccessibleName();
    }

    const css = readFileSync(path.resolve(__dirname, '../../app/globals.css'), 'utf8');
    const token = (name: string) => css.match(new RegExp(`--ff-${name}:\\s*(#[0-9a-f]{6});`))![1];
    expect(contrast(token('danger'), token('bg'))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token('danger'), token('surface'))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token('accent'), '#ffffff')).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token('text-muted'), token('surface'))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token('text-muted'), token('bg'))).toBeGreaterThanOrEqual(4.5);
  });
});

describe('Exportar os meus dados', () => {
  const zipResponse = () =>
    new Response(new Blob(['PK']), {
      status: 200,
      headers: { 'Content-Type': 'application/zip', 'Content-Disposition': 'attachment; filename="Invoflow_meus_dados_20261119_101500.zip"' },
    });

  let clicked: string[];
  let clickSpy: { mockRestore: () => void };

  beforeEach(() => {
    clicked = [];
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this.download);
    });
    vi.mocked(global.fetch).mockReset();
  });

  afterEach(() => {
    clickSpy.mockRestore();
    localStorage.removeItem(DEMO_AUTH_KEY);
    vi.unstubAllEnvs();
  });

  it('is enabled, describes the archive, and stays busy until the ZIP arrives, then downloads it', async () => {
    let resolve!: (r: Response) => void;
    vi.mocked(global.fetch).mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    signInDemo();
    renderSettings();

    const button = await screen.findByRole('button', { name: 'Exportar os meus dados' });
    expect(button).toBeEnabled();
    expect(button).toHaveAccessibleDescription(
      'Um ficheiro ZIP com os seus recibos, os dados de cada documento e o IVA das vendas que introduziu.',
    );
    expect(screen.queryByText('Disponível em breve')).not.toBeInTheDocument();

    fireEvent.click(button);
    await waitFor(() => expect(button).toHaveAttribute('aria-busy', 'true'));
    expect(button).toBeDisabled();
    expect(screen.getByRole('status', { name: '' })).toHaveTextContent('A preparar o ficheiro…');
    const [url, init] = vi.mocked(global.fetch).mock.calls[0];
    expect(url).toBe('/api/account/export');
    expect((init as RequestInit).headers).toEqual({ 'X-Mock-User-Id': expect.stringMatching(/^demo-/) });

    await act(async () => {
      resolve(zipResponse());
    });
    await waitFor(() => expect(button).not.toHaveAttribute('aria-busy'));
    expect(button).toBeEnabled();
    expect(clicked).toEqual(['Invoflow_meus_dados_20261119_101500.zip']);
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows an error toast when the export fails, and clears it on Fechar', async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response('{}', { status: 500 }));
    signInDemo();
    renderSettings();

    const button = await screen.findByRole('button', { name: 'Exportar os meus dados' });
    await act(async () => {
      fireEvent.click(button);
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível exportar os seus dados. Tente novamente.');
    expect(clicked).toEqual([]);
    expect(button).toBeEnabled();
    expect(button).not.toHaveAttribute('aria-busy');

    fireEvent.click(screen.getByRole('button', { name: 'Fechar' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('when rate limited, names the wait in a calm status and counts down on the button until it re-enables', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      vi.mocked(global.fetch)
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ detail: 'Demasiados pedidos. Aguarde 50 s e tente novamente.', error: { code: 'RATE_LIMITED' } }),
            { status: 429, headers: { 'Content-Type': 'application/json', 'Retry-After': '3' } },
          ),
        )
        .mockResolvedValueOnce(zipResponse());
      signInDemo();
      renderSettings();

      await act(async () => {
        fireEvent.click(await screen.findByRole('button', { name: 'Exportar os meus dados' }));
      });

      const notice = await screen.findByTestId('rate-limit-notice');
      expect(notice).toHaveAttribute('role', 'status');
      expect(notice).toHaveTextContent('Aguarde um momento. Pode tentar de novo dentro de 3 s.');
      expect(notice.textContent).not.toMatch(/Tente (novamente|outra vez)/i);
      expect(notice.outerHTML).not.toMatch(/red-|danger/);
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();

      const button = screen.getByRole('button', { name: 'Tentar de novo em 3 s' });
      expect(button).toBeDisabled();
      expect(button.closest('[aria-live],[role="status"],[role="alert"]')).toBeNull();

      act(() => vi.advanceTimersByTime(1000));
      expect(screen.getByRole('button', { name: 'Tentar de novo em 2 s' })).toBeDisabled();
      expect(screen.getByTestId('rate-limit-notice')).toBe(notice);
      expect(notice).toHaveTextContent('dentro de 3 s');

      act(() => vi.advanceTimersByTime(2000));
      const again = screen.getByRole('button', { name: 'Exportar os meus dados' });
      expect(again).toBeEnabled();
      expect(screen.queryByTestId('rate-limit-notice')).not.toBeInTheDocument();

      await act(async () => {
        fireEvent.click(again);
      });
      await waitFor(() => expect(clicked).toEqual(['Invoflow_meus_dados_20261119_101500.zip']));
    } finally {
      vi.useRealTimers();
    }
  });

  it('renders the 429 status in body-text tokens with at least 4.5:1 contrast on the page and card backgrounds', () => {
    const css = readFileSync(path.resolve(__dirname, '../../app/globals.css'), 'utf8');
    const token = (name: string) => css.match(new RegExp(`--ff-${name}:\\s*(#[0-9a-f]{6});`))![1];
    expect(contrast(token('text'), token('surface'))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token('text'), token('bg'))).toBeGreaterThanOrEqual(4.5);
  });

  it('shows the error toast when the network request throws', async () => {
    vi.mocked(global.fetch).mockRejectedValue(new TypeError('Failed to fetch'));
    signInDemo();
    renderSettings();

    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: 'Exportar os meus dados' }));
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível exportar os seus dados. Tente novamente.');
  });
});

describe('delete account, when an API exists and NEXT_PUBLIC_ACCOUNT_DELETE=1', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('matches ELIMINAR exactly: not eliminar, not with a trailing space', () => {
    expect(isDeleteConfirmed('ELIMINAR')).toBe(true);
    expect(isDeleteConfirmed('eliminar')).toBe(false);
    expect(isDeleteConfirmed('ELIMINAR ')).toBe(false);
    expect(isDeleteConfirmed(' ELIMINAR')).toBe(false);
  });

  it('stays at step 1 with the flag off, even with an API', () => {
    render(<DeleteAccountSheet onClose={vi.fn()} onDelete={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Continuar' })).toBeDisabled();
  });

  it('enables the danger button only for exact ELIMINAR, then reports success', async () => {
    vi.stubEnv('NEXT_PUBLIC_ACCOUNT_DELETE', '1');
    const onDelete = vi.fn().mockResolvedValue(undefined);
    const onDeleted = vi.fn();
    render(<DeleteAccountSheet onClose={vi.fn()} onDelete={onDelete} onDeleted={onDeleted} />);

    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));
    const input = screen.getByLabelText('Escreva ELIMINAR para confirmar');
    const confirm = screen.getByRole('button', { name: 'Eliminar conta' });
    expect(confirm).toHaveClass('btn-danger');
    expect(confirm).toBeDisabled();

    fireEvent.change(input, { target: { value: 'eliminar' } });
    expect(confirm).toBeDisabled();
    fireEvent.change(input, { target: { value: 'ELIMINAR ' } });
    expect(confirm).toBeDisabled();
    fireEvent.submit(input.closest('form')!);
    expect(onDelete).not.toHaveBeenCalled();

    fireEvent.change(input, { target: { value: 'ELIMINAR' } });
    expect(confirm).toBeEnabled();
    await act(async () => {
      fireEvent.click(confirm);
    });
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onDeleted).toHaveBeenCalledTimes(1);
  });

  it('keeps the sheet open with an alert when deletion fails', async () => {
    vi.stubEnv('NEXT_PUBLIC_ACCOUNT_DELETE', '1');
    const onDeleted = vi.fn();
    render(
      <DeleteAccountSheet
        onClose={vi.fn()}
        onDelete={vi.fn().mockRejectedValue(new Error('500'))}
        onDeleted={onDeleted}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));
    fireEvent.change(screen.getByLabelText('Escreva ELIMINAR para confirmar'), { target: { value: 'ELIMINAR' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Eliminar conta' }));
    });

    expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível eliminar a conta. Tente novamente.');
    expect(screen.getByRole('alertdialog', { name: 'Eliminar a conta?' })).toBeInTheDocument();
    expect(onDeleted).not.toHaveBeenCalled();
  });
});

function contrast(a: string, b: string) {
  const luminance = (hex: string) => {
    const [r, g, bl] = [1, 3, 5].map((i) => {
      const c = parseInt(hex.slice(i, i + 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
