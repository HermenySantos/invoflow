'use client';

import { useState, useEffect } from 'react';
import { AppLayout } from '@/components/layout/AppLayout';
import { api, Summary } from '@/lib/api';
import { 
  Download, 
  AlertCircle, 
  CheckCircle, 
  Clock,
  TrendingDown,
  TrendingUp,
  FileWarning
} from 'lucide-react';
import { clsx } from 'clsx';

export default function SummaryPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await api.getSummary({ period_type: 'quarter' });
      setSummary(data);
    } catch (err) {
      setError('Failed to load summary');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
  }, []);

  const handleExport = async () => {
    try {
      setIsExporting(true);
      const url = await api.getExportUrl({ period_type: 'quarter' });
      
      // Trigger download
      const link = document.createElement('a');
      link.href = url;
      link.download = `InvoFlow_Export_${summary?.period || 'export'}.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      setIsExporting(false);
    }
  };

  const formatCurrency = (value: string | null) => {
    if (!value) return '€0.00';
    const num = parseFloat(value);
    return new Intl.NumberFormat('pt-PT', {
      style: 'currency',
      currency: 'EUR',
    }).format(num);
  };

  const ivaPayable = summary ? parseFloat(summary.estimated_iva_payable) : 0;
  const isRefund = ivaPayable < 0;

  return (
    <AppLayout title="Summary">
      <div className="p-4 space-y-4">
        {isLoading ? (
          <div className="space-y-4">
            <div className="card p-6 animate-pulse">
              <div className="h-8 bg-gray-200 rounded w-1/3 mb-4" />
              <div className="h-16 bg-gray-200 rounded w-2/3" />
            </div>
          </div>
        ) : error ? (
          <div className="card p-6 text-center">
            <AlertCircle className="w-12 h-12 text-danger-500 mx-auto mb-3" />
            <p className="text-gray-600">{error}</p>
            <button
              onClick={fetchSummary}
              className="btn-secondary btn-md mt-4"
            >
              Retry
            </button>
          </div>
        ) : summary ? (
          <>
            {/* Main IVA Card */}
            <div className="card p-6">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-500">
                  Estimated IVA for {summary.period}
                </span>
                {isRefund ? (
                  <TrendingDown className="w-5 h-5 text-success-500" />
                ) : (
                  <TrendingUp className="w-5 h-5 text-warning-500" />
                )}
              </div>
              <div className={clsx(
                'text-4xl font-bold',
                isRefund ? 'text-success-600' : 'text-gray-900'
              )}>
                {formatCurrency(summary.estimated_iva_payable)}
              </div>
              <p className="text-sm text-gray-500 mt-1">
                {isRefund ? 'Estimated refund' : 'Estimated to pay'}
              </p>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 gap-3">
              <div className="card p-4">
                <p className="text-sm text-gray-500">Receipts</p>
                <p className="text-2xl font-semibold text-gray-900">
                  {summary.total_documents}
                </p>
              </div>
              <div className="card p-4">
                <p className="text-sm text-gray-500">Total VAT</p>
                <p className="text-2xl font-semibold text-gray-900">
                  {formatCurrency(summary.total_vat)}
                </p>
              </div>
            </div>

            {/* Status Breakdown */}
            <div className="card p-4">
              <h3 className="font-medium text-gray-900 mb-3">Document Status</h3>
              <div className="space-y-2">
                <StatusRow
                  icon={<CheckCircle className="w-4 h-4 text-success-500" />}
                  label="Ready"
                  count={summary.ready_count}
                />
                <StatusRow
                  icon={<FileWarning className="w-4 h-4 text-warning-500" />}
                  label="Needs Review"
                  count={summary.needs_review_count}
                />
                <StatusRow
                  icon={<Clock className="w-4 h-4 text-gray-400" />}
                  label="Processing"
                  count={summary.processing_count}
                />
              </div>
            </div>

            {/* Warnings */}
            {summary.warnings.length > 0 && (
              <div className="card p-4 bg-amber-50 border-amber-200">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <h3 className="font-medium text-amber-900">Attention</h3>
                    <ul className="mt-1 text-sm text-amber-800 space-y-1">
                      {summary.warnings.map((warning, i) => (
                        <li key={i}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* Export Button */}
            <button
              onClick={handleExport}
              disabled={isExporting || summary.total_documents === 0}
              className="btn-primary btn-lg w-full flex items-center justify-center gap-2"
            >
              <Download className="w-5 h-5" />
              {isExporting ? 'Generating...' : 'Send to Accountant'}
            </button>
          </>
        ) : null}
      </div>
    </AppLayout>
  );
}

function StatusRow({
  icon,
  label,
  count,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
}) {
  return (
    <div className="flex items-center justify-between py-1">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-sm text-gray-600">{label}</span>
      </div>
      <span className="text-sm font-medium text-gray-900">{count}</span>
    </div>
  );
}
