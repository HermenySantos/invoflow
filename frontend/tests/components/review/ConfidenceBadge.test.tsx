import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConfidenceBadge, ConfidenceIndicator } from '@/components/review/ConfidenceBadge';

describe('ConfidenceBadge', () => {
  it('renders high confidence badge correctly', () => {
    render(<ConfidenceBadge confidence={95} showLabel />);
    
    expect(screen.getByText('95%')).toBeInTheDocument();
  });

  it('renders medium confidence badge correctly', () => {
    render(<ConfidenceBadge confidence={65} showLabel />);
    
    expect(screen.getByText('65%')).toBeInTheDocument();
  });

  it('renders low confidence badge correctly', () => {
    render(<ConfidenceBadge confidence={30} showLabel />);
    
    expect(screen.getByText('30%')).toBeInTheDocument();
  });

  it('returns null for unknown confidence without showLabel', () => {
    const { container } = render(<ConfidenceBadge confidence={null} />);
    
    expect(container.firstChild).toBeNull();
  });

  it('shows unknown label when showLabel is true and confidence is null', () => {
    render(<ConfidenceBadge confidence={null} showLabel />);
    
    expect(screen.getByText('Desconhecida')).toBeInTheDocument();
  });

  it('shows tooltip on hover', async () => {
    render(<ConfidenceBadge confidence={85} fieldName="Vendor Name" />);
    
    const badge = screen.getByRole('button');
    fireEvent.mouseEnter(badge);
    
    expect(screen.getByRole('tooltip')).toBeInTheDocument();
    expect(screen.getByText(/Vendor Name/)).toBeInTheDocument();
  });

  it('hides tooltip on mouse leave', () => {
    render(<ConfidenceBadge confidence={85} />);
    
    const badge = screen.getByRole('button');
    fireEvent.mouseEnter(badge);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();
    
    fireEvent.mouseLeave(badge);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
});

describe('ConfidenceIndicator', () => {
  it('renders indicator for high confidence', () => {
    const { container } = render(<ConfidenceIndicator confidence={90} />);
    
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('renders indicator for low confidence', () => {
    const { container } = render(<ConfidenceIndicator confidence={30} />);
    
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('returns null for null confidence', () => {
    const { container } = render(<ConfidenceIndicator confidence={null} />);
    
    expect(container.firstChild).toBeNull();
  });

  it('returns null for undefined confidence', () => {
    const { container } = render(<ConfidenceIndicator confidence={undefined} />);
    
    expect(container.firstChild).toBeNull();
  });
});
