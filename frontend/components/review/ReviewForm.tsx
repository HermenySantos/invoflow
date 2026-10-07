'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Document } from '@/lib/api';
import { ConfidenceIndicator } from './ConfidenceBadge';
import { AlertCircle, Calculator, Building2, FileText, Euro } from 'lucide-react';

export interface ReviewFormData {
  vendor_name: string;
  vendor_nif: string;
  invoice_number: string;
  document_date: string;
  net_amount: string;
  vat_amount: string;
  gross_amount: string;
  vat_rate: string;
}

interface FieldConfidence {
  vendor_name?: number;
  vendor_nif?: number;
  invoice_number?: number;
  document_date?: number;
  net_amount?: number;
  vat_amount?: number;
  gross_amount?: number;
  vat_rate?: number;
}

interface ReviewFormProps {
  document: Document;
  fieldConfidence?: FieldConfidence;
  onChange: (data: ReviewFormData) => void;
  errors?: Record<string, string>;
}

export function ReviewForm({ 
  document, 
  fieldConfidence = {},
  onChange,
  errors = {}
}: ReviewFormProps) {
  const [formData, setFormData] = useState<ReviewFormData>({
    vendor_name: document.vendor_name || '',
    vendor_nif: document.vendor_nif || '',
    invoice_number: document.invoice_number || '',
    document_date: document.document_date || '',
    net_amount: document.net_amount || '',
    vat_amount: document.vat_amount || '',
    gross_amount: document.gross_amount || '',
    vat_rate: document.vat_rate || '',
  });

  const [editedFields, setEditedFields] = useState<Set<string>>(new Set());

  // Update parent when form data changes
  useEffect(() => {
    onChange(formData);
  }, [formData, onChange]);

  const handleChange = useCallback((field: keyof ReviewFormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setEditedFields(prev => new Set(prev).add(field));
  }, []);

  // Auto-calculate net amount when gross and VAT are provided
  const calculateNetFromGrossAndVat = useCallback(() => {
    const gross = parseFloat(formData.gross_amount);
    const vat = parseFloat(formData.vat_amount);
    
    if (!isNaN(gross) && !isNaN(vat) && gross > 0) {
      const net = gross - vat;
      if (net >= 0) {
        handleChange('net_amount', net.toFixed(2));
      }
    }
  }, [formData.gross_amount, formData.vat_amount, handleChange]);

  // Auto-calculate VAT rate when amounts are available
  const calculateVatRate = useCallback(() => {
    const net = parseFloat(formData.net_amount);
    const vat = parseFloat(formData.vat_amount);
    
    if (!isNaN(net) && !isNaN(vat) && net > 0) {
      const rate = (vat / net) * 100;
      // Round to common Portuguese VAT rates
      const commonRates = [6, 13, 23];
      const closestRate = commonRates.reduce((prev, curr) => 
        Math.abs(curr - rate) < Math.abs(prev - rate) ? curr : prev
      );
      
      // Only auto-fill if close to a common rate
      if (Math.abs(rate - closestRate) < 2) {
        handleChange('vat_rate', closestRate.toString());
      }
    }
  }, [formData.net_amount, formData.vat_amount, handleChange]);

  const getFieldClass = (fieldName: keyof ReviewFormData) => {
    const baseClass = 'input';
    const errorClass = errors[fieldName] ? 'border-red-500 focus:ring-red-500' : '';
    const editedClass = editedFields.has(fieldName) ? 'ring-2 ring-primary-200' : '';
    return `${baseClass} ${errorClass} ${editedClass}`.trim();
  };

  const isFieldEdited = (fieldName: keyof ReviewFormData) => editedFields.has(fieldName);

  return (
    <div className="space-y-6">
      {/* Vendor Information */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <Building2 className="w-4 h-4 text-gray-500" />
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
            Vendor Information
          </h3>
        </div>
        
        <div className="space-y-4">
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
              Vendor Name
              <ConfidenceIndicator confidence={fieldConfidence.vendor_name} />
              {isFieldEdited('vendor_name') && (
                <span className="text-xs text-primary-600 font-normal">(edited)</span>
              )}
            </label>
            <input
              type="text"
              value={formData.vendor_name}
              onChange={(e) => handleChange('vendor_name', e.target.value)}
              placeholder="Enter vendor name"
              className={getFieldClass('vendor_name')}
              aria-invalid={!!errors.vendor_name}
              aria-describedby={errors.vendor_name ? 'vendor-name-error' : undefined}
            />
            {errors.vendor_name && (
              <p id="vendor-name-error" className="mt-1 text-sm text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errors.vendor_name}
              </p>
            )}
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
              NIF (Tax ID)
              <ConfidenceIndicator confidence={fieldConfidence.vendor_nif} />
              {isFieldEdited('vendor_nif') && (
                <span className="text-xs text-primary-600 font-normal">(edited)</span>
              )}
            </label>
            <input
              type="text"
              value={formData.vendor_nif}
              onChange={(e) => handleChange('vendor_nif', e.target.value.replace(/\D/g, '').slice(0, 9))}
              placeholder="123456789"
              maxLength={9}
              className={getFieldClass('vendor_nif')}
              aria-invalid={!!errors.vendor_nif}
              aria-describedby={errors.vendor_nif ? 'vendor-nif-error' : undefined}
            />
            {errors.vendor_nif && (
              <p id="vendor-nif-error" className="mt-1 text-sm text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errors.vendor_nif}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* Document Information */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <FileText className="w-4 h-4 text-gray-500" />
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
            Document Information
          </h3>
        </div>
        
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
              Invoice Number
              <ConfidenceIndicator confidence={fieldConfidence.invoice_number} />
              {isFieldEdited('invoice_number') && (
                <span className="text-xs text-primary-600 font-normal">(edited)</span>
              )}
            </label>
            <input
              type="text"
              value={formData.invoice_number}
              onChange={(e) => handleChange('invoice_number', e.target.value)}
              placeholder="INV-2024-001"
              className={getFieldClass('invoice_number')}
              aria-invalid={!!errors.invoice_number}
            />
            {errors.invoice_number && (
              <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errors.invoice_number}
              </p>
            )}
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
              Date
              <ConfidenceIndicator confidence={fieldConfidence.document_date} />
              {isFieldEdited('document_date') && (
                <span className="text-xs text-primary-600 font-normal">(edited)</span>
              )}
            </label>
            <input
              type="date"
              value={formData.document_date}
              onChange={(e) => handleChange('document_date', e.target.value)}
              max={new Date().toISOString().split('T')[0]}
              className={getFieldClass('document_date')}
              aria-invalid={!!errors.document_date}
            />
            {errors.document_date && (
              <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errors.document_date}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* Amounts */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <Euro className="w-4 h-4 text-gray-500" />
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
            Amounts
          </h3>
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
              Net Amount (€)
              <ConfidenceIndicator confidence={fieldConfidence.net_amount} />
              {isFieldEdited('net_amount') && (
                <span className="text-xs text-primary-600 font-normal">(edited)</span>
              )}
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={formData.net_amount}
              onChange={(e) => handleChange('net_amount', e.target.value)}
              placeholder="0.00"
              className={getFieldClass('net_amount')}
              aria-invalid={!!errors.net_amount}
            />
            {errors.net_amount && (
              <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errors.net_amount}
              </p>
            )}
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
              VAT Amount (€)
              <ConfidenceIndicator confidence={fieldConfidence.vat_amount} />
              {isFieldEdited('vat_amount') && (
                <span className="text-xs text-primary-600 font-normal">(edited)</span>
              )}
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={formData.vat_amount}
              onChange={(e) => handleChange('vat_amount', e.target.value)}
              placeholder="0.00"
              className={getFieldClass('vat_amount')}
              aria-invalid={!!errors.vat_amount}
            />
            {errors.vat_amount && (
              <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errors.vat_amount}
              </p>
            )}
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
              Gross Amount (€)
              <ConfidenceIndicator confidence={fieldConfidence.gross_amount} />
              {isFieldEdited('gross_amount') && (
                <span className="text-xs text-primary-600 font-normal">(edited)</span>
              )}
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={formData.gross_amount}
              onChange={(e) => handleChange('gross_amount', e.target.value)}
              placeholder="0.00"
              className={getFieldClass('gross_amount')}
              aria-invalid={!!errors.gross_amount}
            />
            {errors.gross_amount && (
              <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errors.gross_amount}
              </p>
            )}
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
              VAT Rate (%)
              <ConfidenceIndicator confidence={fieldConfidence.vat_rate} />
              {isFieldEdited('vat_rate') && (
                <span className="text-xs text-primary-600 font-normal">(edited)</span>
              )}
            </label>
            <select
              value={formData.vat_rate}
              onChange={(e) => handleChange('vat_rate', e.target.value)}
              className={getFieldClass('vat_rate')}
              aria-invalid={!!errors.vat_rate}
            >
              <option value="">Select rate</option>
              <option value="6">6% (Reduced)</option>
              <option value="13">13% (Intermediate)</option>
              <option value="23">23% (Standard)</option>
              <option value="0">0% (Exempt)</option>
            </select>
            {errors.vat_rate && (
              <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errors.vat_rate}
              </p>
            )}
          </div>
        </div>

        {/* Auto-calculate helpers */}
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={calculateNetFromGrossAndVat}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
            title="Calculate Net = Gross - VAT"
          >
            <Calculator className="w-3.5 h-3.5" />
            Calculate Net
          </button>
          <button
            type="button"
            onClick={calculateVatRate}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
            title="Auto-detect VAT rate from amounts"
          >
            <Calculator className="w-3.5 h-3.5" />
            Detect VAT Rate
          </button>
        </div>
      </section>

      {/* OCR Confidence Summary */}
      {document.ocr_confidence && (
        <section className="pt-4 border-t border-gray-200">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500">Overall OCR Confidence</span>
            <span className={`font-semibold ${
              parseFloat(document.ocr_confidence) >= 80 ? 'text-green-600' :
              parseFloat(document.ocr_confidence) >= 50 ? 'text-amber-600' : 'text-red-600'
            }`}>
              {parseFloat(document.ocr_confidence).toFixed(0)}%
            </span>
          </div>
        </section>
      )}
    </div>
  );
}

export default ReviewForm;
