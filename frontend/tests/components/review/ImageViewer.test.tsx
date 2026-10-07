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
    
    expect(screen.getByText('No image available')).toBeInTheDocument();
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
    expect(screen.getByText('PDF preview not available')).toBeInTheDocument();
    expect(screen.getByText('Open PDF')).toBeInTheDocument();
  });

  it('displays zoom controls', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    expect(screen.getByLabelText('Zoom out')).toBeInTheDocument();
    expect(screen.getByLabelText('Zoom in')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('zooms in when zoom in button is clicked', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    const zoomInButton = screen.getByLabelText('Zoom in');
    fireEvent.click(zoomInButton);
    
    expect(screen.getByText('150%')).toBeInTheDocument();
  });

  it('zooms out when zoom out button is clicked', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    // First zoom in
    const zoomInButton = screen.getByLabelText('Zoom in');
    fireEvent.click(zoomInButton);
    expect(screen.getByText('150%')).toBeInTheDocument();
    
    // Then zoom out
    const zoomOutButton = screen.getByLabelText('Zoom out');
    fireEvent.click(zoomOutButton);
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('disables zoom out at minimum zoom', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    const zoomOutButton = screen.getByLabelText('Zoom out');
    expect(zoomOutButton).toBeDisabled();
  });

  it('has fullscreen toggle button', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    expect(screen.getByLabelText('View fullscreen')).toBeInTheDocument();
  });

  it('shows loading skeleton initially', () => {
    render(<ImageViewer src="https://example.com/image.jpg" />);
    
    // The loading spinner should be visible initially
    const img = screen.getByRole('img');
    expect(img).toHaveClass('invisible');
  });
});
