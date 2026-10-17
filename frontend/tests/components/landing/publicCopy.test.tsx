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
    expect(screen.getByText('Exemplo ilustrativo · março de 2026')).toBeInTheDocument();
    expect(screen.getByText('Estimativa')).toBeInTheDocument();
    expect(screen.getByText('Prazo de entrega: 20 de maio de 2026')).toBeInTheDocument();
    expect(screen.getByText(/entra com 0,00 €/)).toBeInTheDocument();
    expect(screen.queryByText(/486/)).not.toBeInTheDocument();
    expect(screen.queryByText(/20 de abril/)).not.toBeInTheDocument();
    if (isDemoMode) {
      expect(screen.getByText(/armazenamento de ficheiros são simulados/)).toBeInTheDocument();
      expect(screen.getByText(/O OCR é simulado/)).toBeInTheDocument();
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
    expect(screen.queryByText('TODO')).not.toBeInTheDocument();
    expect(screen.queryByText(/Confirmar com Gildo/)).not.toBeInTheDocument();
    expect(screen.queryByText(/a confirmar/)).not.toBeInTheDocument();
    expect(screen.getByText('Nome: Hermenegildo Jerónimo dos Santos')).toBeInTheDocument();
    expect(screen.getByText('Morada e NIF disponibilizados mediante pedido')).toBeInTheDocument();
    expect(screen.getAllByText('hermeny7@hotmail.com').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('heading', { name: 'Transferências internacionais' })).toBeInTheDocument();
    expect(screen.getByText(/EU-US Data Privacy Framework/)).toBeInTheDocument();
    expect(screen.getAllByText(/incluindo NIFs/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Hetzner/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Cloudflare R2/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Clerk/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Sentry/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('heading', { name: 'Direitos' })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('pt');
    fireEvent.click(screen.getByRole('button', { name: 'EN' }));
    expect(document.documentElement.lang).toBe('en');
    fireEvent.click(screen.getByRole('button', { name: 'PT' }));
    expect(document.documentElement.lang).toBe('pt');
    fireEvent.click(screen.getByRole('button', { name: 'EN' }));
    expect(document.documentElement.lang).toBe('en');
  });

  it('switches to the English notice', () => {
    render(<PrivacyPage />);
    fireEvent.click(screen.getByRole('button', { name: 'EN' }));

    expect(screen.getByRole('heading', { name: 'Privacy' })).toBeInTheDocument();
    expect(screen.queryByText('TODO')).not.toBeInTheDocument();
    expect(screen.getByText('Name: Hermenegildo Jerónimo dos Santos')).toBeInTheDocument();
    expect(screen.getByText('Address and NIF are available on request')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'International transfers' })).toBeInTheDocument();
    expect(screen.getAllByText(/including NIFs/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('heading', { name: 'Your rights' })).toBeInTheDocument();
  });
});
