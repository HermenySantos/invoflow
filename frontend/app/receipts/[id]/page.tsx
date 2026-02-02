'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AppLayout } from '@/components/layout/AppLayout';
import { api, Document } from '@/lib/api';
import { 
  ArrowLeft, 
  AlertCircle, 
  CheckCircle, 
  Trash2,
  Save
} from 'lucide-react';
import Link from 'next/link';

export default function ReceiptDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [document, setDocument] = useState<Document | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Editable fields
  const [vendorName, setVendorName] = useState('');
  const [grossAmount, setGrossAmount] = useState('');
  const [vatAmount, setVatAmount] = useState('');
  const [documentDate, setDocumentDate] = useState('');

  const fetchDocument = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await api.getDocument(params.id as string);
      setDocument(data);
      
      // Populate form fields
      setVendorName(data.vendor_name || '');
      setGrossAmount(data.gross_amount || '');
      setVatAmount(data.vat_amount || '');
      setDocumentDate(data.document_date || '');
    } catch (err) {
      setError('Failed to load receipt');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDocument();
  }, [params.id]);

  const handleSave = async () => {
    if (!document) return;
    
    try {
      setIsSaving(true);
      await api.updateDocument(document.id, {
        vendor_name: vendorName || null,
        gross_amount: grossAmount || null,
        vat_amount: vatAmount || null,
        document_date: documentDate || null,
        status: 'ready', // Mark as reviewed
      });
      router.push('/receipts');
    } catch (err) {
      console.error('Failed to save:', err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!document) return;
    if (!confirm('Are you sure you want to delete this receipt?')) return;
    
    try {
      await api.deleteDocument(document.id);
      router.push('/receipts');
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  const formatCurrency = (value: string | null) => {
    if (!value) return '-';
    const num = parseFloat(value);
    return new Intl.NumberFormat('pt-PT', {
      style: 'currency',
      currency: 'EUR',
    }).format(num);
  };

  return (
    <AppLayout>
      {/* Custom header with back button */}
      <header className="sticky top-0 z-40 bg-white border-b border-gray-200">
        <div className="flex items-center justify-between h-14 px-4">
          <Link href="/receipts" className="p-2 -ml-2">
            <ArrowLeft className="w-5 h-5 text-gray-600" />
          </Link>
          <h1 className="text-lg font-semibold text-gray-900">Receipt Details</h1>
          <button
            onClick={handleDelete}
            className="p-2 -mr-2 text-danger-500"
          >
            <Trash2 className="w-5 h-5" />
          </button>
        </div>
      </header>

      <div className="p-4 space-y-4">
        {isLoading ? (
          <div className="space-y-4">
            <div className="card aspect-[4/3] animate-pulse bg-gray-200" />
            <div className="card p-4 space-y-3 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/3" />
              <div className="h-10 bg-gray-200 rounded" />
            </div>
          </div>
        ) : error ? (
          <div className="card p-6 text-center">
            <AlertCircle className="w-12 h-12 text-danger-500 mx-auto mb-3" />
            <p className="text-gray-600">{error}</p>
          </div>
        ) : document ? (
          <>
            {/* Image preview */}
            {document.file_url && (
              <div className="card overflow-hidden">
                <img
                  src={document.file_url}
                  alt="Receipt"
                  className="w-full object-contain max-h-64 bg-gray-100"
                />
              </div>
            )}

            {/* Status badge */}
            {document.status === 'needs_review' && (
              <div className="card p-3 bg-amber-50 border-amber-200 flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-amber-600" />
                <span className="text-sm text-amber-800">
                  This receipt needs review. Please verify the extracted data.
                </span>
              </div>
            )}

            {/* Editable form */}
            <div className="card p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Vendor Name
                </label>
                <input
                  type="text"
                  value={vendorName}
                  onChange={(e) => setVendorName(e.target.value)}
                  placeholder="Enter vendor name"
                  className="input"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Date
                </label>
                <input
                  type="date"
                  value={documentDate}
                  onChange={(e) => setDocumentDate(e.target.value)}
                  className="input"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Total (€)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={grossAmount}
                    onChange={(e) => setGrossAmount(e.target.value)}
                    placeholder="0.00"
                    className="input"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    VAT (€)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={vatAmount}
                    onChange={(e) => setVatAmount(e.target.value)}
                    placeholder="0.00"
                    className="input"
                  />
                </div>
              </div>

              {/* OCR confidence indicator */}
              {document.ocr_confidence && (
                <div className="pt-2 border-t border-gray-100">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-500">OCR Confidence</span>
                    <span className="font-medium">
                      {parseFloat(document.ocr_confidence).toFixed(0)}%
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Save button */}
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="btn-primary btn-lg w-full flex items-center justify-center gap-2"
            >
              {document.status === 'needs_review' ? (
                <>
                  <CheckCircle className="w-5 h-5" />
                  {isSaving ? 'Saving...' : 'Mark as Reviewed'}
                </>
              ) : (
                <>
                  <Save className="w-5 h-5" />
                  {isSaving ? 'Saving...' : 'Save Changes'}
                </>
              )}
            </button>
          </>
        ) : null}
      </div>
    </AppLayout>
  );
}
