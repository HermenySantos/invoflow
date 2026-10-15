import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LandingPage } from '@/components/landing/LandingPage';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { isDemoMode } from '@/lib/demoUser';
import { PrivacyPage } from '@/app/privacy/PrivacyPage';

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

describe('landing pilot and limits', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', memoryStorage());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the pilot offer, the sales-VAT limit, and demo mode', () => {
    render(
      <AuthProvider>
        <LandingPage />
      </AuthProvider>,
    );

    expect(screen.getByRole('heading', { name: 'Pack IVA' })).toBeInTheDocument();
    expect(screen.getByText('~190 €')).toBeInTheDocument();
    expect(screen.getByText('por trimestre')).toBeInTheDocument();
    expect(screen.getByText(/primeiro trimestre com desconto/)).toBeInTheDocument();
    expect(screen.getByText('Carregar faturas e recibos')).toBeInTheDocument();
    expect(screen.getByText('Estimativa de IVA')).toBeInTheDocument();
    expect(screen.getByText(/pronto para o contabilista/)).toBeInTheDocument();
    expect(screen.getByText(/não substitui o contabilista/)).toBeInTheDocument();
    expect(screen.getByText(/Este valor ignora o IVA das vendas/)).toBeInTheDocument();
    if (isDemoMode) {
      expect(screen.getByText(/armazenamento de ficheiros são simulados/)).toBeInTheDocument();
    }
  });
});

describe('privacy notice', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', memoryStorage());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('states the controller placeholders, NIFs, processors, and contact', () => {
    render(<PrivacyPage />);

    expect(screen.getByRole('heading', { name: 'Privacidade' })).toBeInTheDocument();
    expect(screen.getAllByText('TODO').length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText('Nome: Hermenegildo Jerónimo dos Santos').closest('li')).not.toHaveTextContent('TODO');
    expect(screen.getByText('Morada completa do responsável').closest('li')).toHaveTextContent('TODO');
    expect(screen.getByText('NIF do responsável pelo tratamento').closest('li')).toHaveTextContent('TODO');
    expect(screen.getAllByText('hermeny7@hotmail.com').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('(a confirmar)').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/incluindo NIFs/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Hetzner/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Cloudflare R2/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Clerk/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Sentry/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('heading', { name: 'Direitos' })).toBeInTheDocument();
  });

  it('switches to the English notice', () => {
    render(<PrivacyPage />);
    fireEvent.click(screen.getByRole('button', { name: 'EN' }));

    expect(screen.getByRole('heading', { name: 'Privacy' })).toBeInTheDocument();
    expect(screen.getByText('Name: Hermenegildo Jerónimo dos Santos').closest('li')).not.toHaveTextContent('TODO');
    expect(screen.getByText('Controller’s full postal address').closest('li')).toHaveTextContent('TODO');
    expect(screen.getByText('Controller’s tax identification number (NIF)').closest('li')).toHaveTextContent('TODO');
    expect(screen.getAllByText('(to confirm)').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/including NIFs/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('heading', { name: 'Your rights' })).toBeInTheDocument();
  });
});
