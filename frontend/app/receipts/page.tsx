'use client';

import { useState, useEffect } from 'react';
import { AppLayout } from '@/components/layout/AppLayout';
import { api, Document } from '@/lib/api';
import { 
  Receipt, 
  AlertCircle, 
  CheckCircle, 
  Clock, 
  XCircle,
  ChevronRight,
  RefreshCw
} from 'lucide-react';
import { clsx } from 'clsx';
import Link from 'next/link';

export default function ReceiptsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await api.getDocuments({ page_size: 50 });
      setDocuments(data.documents);
    } catch (err) {
      setError('Failed to load receipts');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'No date';
    return new Date(dateStr).toLocaleDateString('pt-PT', {
      day: 'numeric',
      month: 'short',
    });
  };

  const formatCurrency = (value: string | null) => {
    if (!value) return '-';
    const num = parseFloat(value);
    return new Intl.NumberFormat('pt-PT', {
      style: 'currency',
      currency: 'EUR',
    }).format(num);
  };

  const getStatusIcon = (status: Document['status']) => {
    switch (status) {
      case 'ready':
        return <CheckCircle className="w-4 h-4 text-success-500" />;
      case 'needs_review':
        return <AlertCircle className="w-4 h-4 text-warning-500" />;
      case 'processing':
      case 'pending':
        return <Clock className="w-4 h-4 text-gray-400 animate-pulse" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-danger-500" />;
    }
  };

  return (
    <AppLayout title="Receipts">
      <div className="p-4">
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="card p-4 animate-pulse">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-gray-200 rounded-lg" />
                  <div className="flex-1">
                    <div className="h-4 bg-gray-200 rounded w-1/2 mb-2" />
                    <div className="h-3 bg-gray-200 rounded w-1/3" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="card p-6 text-center">
            <AlertCircle className="w-12 h-12 text-danger-500 mx-auto mb-3" />
            <p className="text-gray-600">{error}</p>
            <button
              onClick={fetchDocuments}
              className="btn-secondary btn-md mt-4"
            >
              Retry
            </button>
          </div>
        ) : documents.length === 0 ? (
          <div className="card p-8 text-center">
            <Receipt className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-1">
              No receipts yet
            </h3>
            <p className="text-gray-500 mb-4">
              Scan your first receipt to get started
            </p>
            <Link href="/scan" className="btn-primary btn-md">
              Scan Receipt
            </Link>
          </div>
        ) : (
          <>
            {/* Refresh button */}
            <div className="flex justify-end mb-3">
              <button
                onClick={fetchDocuments}
                className="btn-secondary btn-sm flex items-center gap-1"
              >
                <RefreshCw className="w-4 h-4" />
                Refresh
              </button>
            </div>

            {/* Document list */}
            <div className="space-y-2">
              {documents.map((doc) => (
                <Link
                  key={doc.id}
                  href={`/receipts/${doc.id}`}
                  className="card p-4 flex items-center gap-3 hover:bg-gray-50 transition-colors"
                >
                  {/* Thumbnail or icon */}
                  <div className="w-12 h-12 bg-gray-100 rounded-lg flex items-center justify-center flex-shrink-0 overflow-hidden">
                    {doc.file_url ? (
                      <img
                        src={doc.file_url}
                        alt=""
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                        }}
                      />
                    ) : (
                      <Receipt className="w-6 h-6 text-gray-400" />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900 truncate">
                        {doc.vendor_name || 'Unknown Vendor'}
                      </span>
                      {getStatusIcon(doc.status)}
                    </div>
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <span>{formatDate(doc.document_date || doc.created_at)}</span>
                      <span>•</span>
                      <span className="font-medium text-gray-700">
                        {formatCurrency(doc.gross_amount)}
                      </span>
                    </div>
                  </div>

                  <ChevronRight className="w-5 h-5 text-gray-400" />
                </Link>
              ))}
            </div>
          </>
        )}
      </div>
    </AppLayout>
  );
}
