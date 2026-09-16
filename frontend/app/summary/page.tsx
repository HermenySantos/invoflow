'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { AppLayout } from '@/components/layout/AppLayout';
import { api, Summary } from '@/lib/api';
import {
  AlertCircle,
  CheckCircle,
  Clock,
  Download,
  FileWarning,
  Receipt,
} from 'lucide-react';
import { clsx } from 'clsx';

export default function SummaryPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [periodType, setPeriodType] = useState<'quarter' | 'month'>('quarter');
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const fetchSummary = async (type: 'quarter' | 'month' = periodType) => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await api.getSummary({ period_type: type });
      setSummary(data);
    } catch (err) {
      setError('Não foi possível carregar o resumo de IVA.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary(periodType);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodType]);

  const handleExport = async () => {
    try {
      setIsExporting(true);
      setExportError(null);
      const { blob, filename } = await api.downloadExport({ period_type: periodType });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
      setExportError('O pacote não foi gerado. Tente outra vez.');
    } finally {
      setIsExporting(false);
    }
  };

  const formatCurrency = (value: string | null) => {
    if (!value) return '€0,00';
    const num = parseFloat(value);
    return new Intl.NumberFormat('pt-PT', {
      style: 'currency',
      currency: 'EUR',
    }).format(num);
  };

  const ivaPayable = summary ? parseFloat(summary.estimated_iva_payable) : 0;
  const isRefund = ivaPayable < 0;

  return (
    <AppLayout title="Resumo IVA">
      <div className="p-4 space-y-4">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setPeriodType('quarter')}
            className={clsx(
              'btn-sm',
              periodType === 'quarter' ? 'btn-primary' : 'btn-secondary'
            )}
          >
            Trimestre
          </button>
          <button
            type="button"
            onClick={() => setPeriodType('month')}
            className={clsx(
              'btn-sm',
              periodType === 'month' ? 'btn-primary' : 'btn-secondary'
            )}
          >
            Mês
          </button>
        </div>

        {isLoading ? (
          <div className="card p-6 text-sm text-gray-500">A calcular o período…</div>
        ) : error ? (
          <div className="card p-6 text-center">
            <AlertCircle className="w-12 h-12 text-danger-500 mx-auto mb-3" />
            <p className="text-gray-600">{error}</p>
            <button onClick={() => fetchSummary()} className="btn-secondary btn-md mt-4">
              Tentar outra vez
            </button>
          </div>
        ) : summary && summary.total_documents === 0 ? (
          <div className="card p-8 text-center">
            <Receipt className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium mb-1">Ainda sem documentos neste período</h3>
            <p className="text-gray-500 mb-4">
              Carregue um recibo para ver a estimativa de IVA e gerar o pacote.
            </p>
            <Link href="/upload" className="btn-primary btn-md">
              Carregar recibo
            </Link>
          </div>
        ) : summary ? (
          <>
            <div className="card p-6">
              <p className="text-sm text-gray-500 mb-2">
                Estimativa de IVA · {summary.period}
              </p>
              <div
                className={clsx(
                  'text-4xl font-semibold',
                  isRefund ? 'text-success-600' : 'text-gray-900'
                )}
              >
                {formatCurrency(summary.estimated_iva_payable)}
              </div>
              <p className="text-sm text-gray-500 mt-1">
                {isRefund ? 'Estimativa a favor (revisão)' : 'Estimativa a pagar (revisão)'}
              </p>
              <p className="text-xs text-gray-400 mt-3">
                IVA sobre vendas ainda não entra neste cálculo. Revê sempre antes de enviar.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="card p-4">
                <p className="text-sm text-gray-500">Documentos</p>
                <p className="text-2xl font-semibold">{summary.total_documents}</p>
              </div>
              <div className="card p-4">
                <p className="text-sm text-gray-500">IVA nos recibos</p>
                <p className="text-2xl font-semibold">{formatCurrency(summary.total_vat)}</p>
              </div>
            </div>

            <div className="card p-4">
              <h3 className="font-medium mb-3">Estado</h3>
              <StatusRow
                icon={<CheckCircle className="w-4 h-4 text-success-500" />}
                label="Prontos"
                count={summary.ready_count}
              />
              <StatusRow
                icon={<FileWarning className="w-4 h-4 text-warning-500" />}
                label="A rever"
                count={summary.needs_review_count}
              />
              <StatusRow
                icon={<Clock className="w-4 h-4 text-gray-400" />}
                label="A processar"
                count={summary.processing_count}
              />
            </div>

            {summary.warnings.length > 0 && (
              <div className="card p-4 border-amber-200 bg-amber-50">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <ul className="text-sm text-amber-800 space-y-1">
                    {summary.warnings.map((warning, i) => (
                      <li key={i}>{warning}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {exportError && (
              <p className="text-sm text-danger-500">{exportError}</p>
            )}

            <button
              onClick={handleExport}
              disabled={isExporting}
              className="btn-primary btn-lg w-full flex items-center justify-center gap-2"
            >
              <Download className="w-5 h-5" />
              {isExporting ? 'A gerar…' : 'Descarregar pacote do contabilista'}
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
      <span className="text-sm font-medium">{count}</span>
    </div>
  );
}
