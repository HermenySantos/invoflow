import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReviewForm } from '@/components/review/ReviewForm';
import { Document } from '@/lib/api';

const mockDocument: Document = {
  id: '123',
  user_id: 'user-1',
  status: 'needs_review',
  storage_key: 'test/key',
  original_filename: 'receipt.jpg',
  mime_type: 'image/jpeg',
  file_size: 1024,
  vendor_name: 'Test Vendor',
  vendor_nif: '123456789',
  invoice_number: 'INV-001',
  document_date: '2024-01-15',
  net_amount: '81.30',
  vat_amount: '18.70',
  gross_amount: '100.00',
  vat_rate: '23',
  ocr_confidence: '85.5',
  field_confidence: null,
  review_notes: null,
  expense_category: 'food',
  irs_sector: 'geral',
  period_tag: '2024-01',
  quarter_tag: '2024-Q1',
  file_url: null,
  thumbnail_url: null,
  validation_warnings: [],
  created_at: '2024-01-15T10:00:00Z',
  updated_at: '2024-01-15T10:00:00Z',
};

describe('ReviewForm', () => {
  it('renders all form sections', () => {
    const onChange = vi.fn();
    render(<ReviewForm document={mockDocument} onChange={onChange} />);
    
    // Check for section headings
    expect(screen.getByText('Vendor Information')).toBeInTheDocument();
    expect(screen.getByText('Document Information')).toBeInTheDocument();
    expect(screen.getByText('Amounts')).toBeInTheDocument();
    
    // Check key field labels exist
    expect(screen.getByText('Vendor Name')).toBeInTheDocument();
    expect(screen.getByText('Date')).toBeInTheDocument();
  });

  it('populates fields with document data', () => {
    const onChange = vi.fn();
    render(<ReviewForm document={mockDocument} onChange={onChange} />);
    
    expect(screen.getByDisplayValue('Test Vendor')).toBeInTheDocument();
    expect(screen.getByDisplayValue('123456789')).toBeInTheDocument();
    expect(screen.getByDisplayValue('INV-001')).toBeInTheDocument();
    expect(screen.getByDisplayValue('100.00')).toBeInTheDocument();
  });

  it('calls onChange when field is updated', () => {
    const onChange = vi.fn();
    render(<ReviewForm document={mockDocument} onChange={onChange} />);
    
    const vendorInput = screen.getByDisplayValue('Test Vendor');
    fireEvent.change(vendorInput, { target: { value: 'New Vendor' } });
    
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ vendor_name: 'New Vendor' })
    );
  });

  it('displays validation errors', () => {
    const onChange = vi.fn();
    const errors = {
      vendor_name: 'Vendor name is required',
      gross_amount: 'Must be a positive number',
    };
    
    render(<ReviewForm document={mockDocument} onChange={onChange} errors={errors} />);
    
    expect(screen.getByText('Vendor name is required')).toBeInTheDocument();
    expect(screen.getByText('Must be a positive number')).toBeInTheDocument();
  });

  it('shows field sections with icons', () => {
    const onChange = vi.fn();
    render(<ReviewForm document={mockDocument} onChange={onChange} />);
    
    expect(screen.getByText('Vendor Information')).toBeInTheDocument();
    expect(screen.getByText('Document Information')).toBeInTheDocument();
    expect(screen.getByText('Amounts')).toBeInTheDocument();
  });

  it('shows OCR confidence summary', () => {
    const onChange = vi.fn();
    render(<ReviewForm document={mockDocument} onChange={onChange} />);
    
    expect(screen.getByText('Overall OCR Confidence')).toBeInTheDocument();
    expect(screen.getByText('86%')).toBeInTheDocument();
  });

  it('has calculate helpers buttons', () => {
    const onChange = vi.fn();
    render(<ReviewForm document={mockDocument} onChange={onChange} />);
    
    expect(screen.getByText('Calculate Net')).toBeInTheDocument();
    expect(screen.getByText('Detect VAT Rate')).toBeInTheDocument();
  });

  it('restricts NIF input to 9 digits', () => {
    const onChange = vi.fn();
    render(<ReviewForm document={mockDocument} onChange={onChange} />);
    
    const nifInput = screen.getByDisplayValue('123456789');
    fireEvent.change(nifInput, { target: { value: '12345678901234' } });
    
    // Should only keep first 9 digits
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ vendor_nif: '123456789' })
    );
  });

  it('shows edited indicator when field is modified', () => {
    const onChange = vi.fn();
    render(<ReviewForm document={mockDocument} onChange={onChange} />);
    
    const vendorInput = screen.getByDisplayValue('Test Vendor');
    fireEvent.change(vendorInput, { target: { value: 'Modified Vendor' } });
    
    expect(screen.getByText('(edited)')).toBeInTheDocument();
  });
});
