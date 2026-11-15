import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ImageViewer } from '@/components/review/ImageViewer';

describe('ImageViewer', () => {
  it('renders image with correct src', () => {
    render(<ImageViewer src="https://example.com/image.jpg" alt="Test image" />);
    
    const img = screen.getByRole('img');
    expect(img).toHaveAttribute('src', 'https://example.com/image.jpg');
    expect(img).toHaveAttribute('alt', 'Test image');
  });

  it('shows placeholder when no src provided', () => {
    render(<ImageViewer src={null} />);
    
    expect(screen.getByText('Sem imagem disponível')).toBeInTheDocument();
  });

  it('shows PDF placeholder for PDF files', () => {
    render(
      <ImageViewer 
        src="https://example.com/doc.pdf" 
        mimeType="application/pdf"
        filename="invoice.pdf"
      />
    );
    
    expect(screen.getByText('invoice.pdf')).toBeInTheDocument();
    expect(screen.getByText('Pré-visualização de PDF indisponível')).toBeInTheDocument();
    expect(screen.getByText('Abrir PDF')).toBeInTheDocument();
  });

  it('displays zoom controls', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    expect(screen.getByLabelText('Reduzir')).toBeInTheDocument();
    expect(screen.getByLabelText('Ampliar')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('gives the zoom controls 44 px on touch screens and keeps 36 px from lg up', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);

    // 16 px icon plus p-3.5 on each side is 44 px; lg:p-2.5 is the previous 36 px.
    for (const name of ['Reduzir', 'Ampliar', 'Ver em ecrã inteiro']) {
      const button = screen.getByLabelText(name);
      expect(button.classList.contains('p-3.5')).toBe(true);
      expect(button.classList.contains('lg:p-2.5')).toBe(true);
    }
    const hint = screen.getByText('Toque duas vezes para ampliar');
    expect(hint.classList.contains('top-3')).toBe(true);
    expect(hint.classList.contains('bottom-3')).toBe(false);
  });

  it('zooms in when zoom in button is clicked', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    const zoomInButton = screen.getByLabelText('Ampliar');
    fireEvent.click(zoomInButton);
    
    expect(screen.getByText('150%')).toBeInTheDocument();
  });

  it('zooms out when zoom out button is clicked', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    // First zoom in
    const zoomInButton = screen.getByLabelText('Ampliar');
    fireEvent.click(zoomInButton);
    expect(screen.getByText('150%')).toBeInTheDocument();
    
    // Then zoom out
    const zoomOutButton = screen.getByLabelText('Reduzir');
    fireEvent.click(zoomOutButton);
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('disables zoom out at minimum zoom', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    const zoomOutButton = screen.getByLabelText('Reduzir');
    expect(zoomOutButton).toBeDisabled();
  });

  it('has fullscreen toggle button', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    expect(screen.getByLabelText('Ver em ecrã inteiro')).toBeInTheDocument();
  });

  it('shows loading skeleton initially', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    // The loading spinner should be visible initially
    const img = screen.getByRole('img');
    expect(img).toHaveClass('invisible');
  });
});
