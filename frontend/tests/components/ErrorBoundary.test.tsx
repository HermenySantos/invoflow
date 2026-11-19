import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from '@/components/ErrorBoundary';

let shouldThrow = true;

const MaybeThrow = () => {
  if (shouldThrow) {
    throw new Error('Test error');
  }
  return <div>Conteúdo recuperado</div>;
};

const ENGLISH = /\b(something went wrong|unexpected|try again|reload|page|error|go to|receipts?)\b/i;

describe('ErrorBoundary', () => {
  beforeEach(() => {
    shouldThrow = true;
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div>Child content</div>
      </ErrorBoundary>
    );

    expect(screen.getByText('Child content')).toBeInTheDocument();
  });

  it('renders the approved PT-PT fallback with no English UI strings', () => {
    const { container } = render(
      <ErrorBoundary>
        <MaybeThrow />
      </ErrorBoundary>
    );

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Algo correu mal');
    expect(
      screen.getByText('Não conseguimos mostrar esta página. Pode tentar outra vez ou voltar aos recibos.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar outra vez' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Recarregar a página' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ir para os recibos' })).toHaveAttribute('href', '/receipts');
    expect(container.textContent).not.toMatch(ENGLISH);
  });

  it('renders custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={<div>Custom fallback</div>}>
        <MaybeThrow />
      </ErrorBoundary>
    );

    expect(screen.getByText('Custom fallback')).toBeInTheDocument();
  });

  it('recovers when "Tentar outra vez" is pressed and the child no longer throws', () => {
    render(
      <ErrorBoundary>
        <MaybeThrow />
      </ErrorBoundary>
    );

    shouldThrow = false;
    fireEvent.click(screen.getByRole('button', { name: 'Tentar outra vez' }));

    expect(screen.getByText('Conteúdo recuperado')).toBeInTheDocument();
  });

  it('keeps retry and reload at 44 px with the accent on the primary', () => {
    render(
      <ErrorBoundary>
        <MaybeThrow />
      </ErrorBoundary>
    );

    const retry = screen.getByRole('button', { name: 'Tentar outra vez' });
    const reload = screen.getByRole('button', { name: 'Recarregar a página' });
    for (const button of [retry, reload]) {
      expect(button.className).toContain('min-h-11');
      expect(button.className).toContain('lg:min-h-11');
    }
    expect(retry.className).toContain('btn-primary');
    expect(screen.getByRole('link', { name: 'Ir para os recibos' }).className).toContain('min-h-11');
  });
});
