'use client';

import { useState, useEffect, useCallback, useMemo } from "react";
import { AppLayout } from '@/components/layout/AppLayout';
import { parseAmountInput } from "@/lib/amount";
import { api, Summary, CategoryBreakdown } from "@/lib/api";
import { getExpenseCategoryInfo, getIrsSectorInfo } from "@/lib/categories";
import {
  Download,
  AlertCircle,
  CheckCircle,
  Clock,
  TrendingDown,
  TrendingUp,
  FileWarning,
  Tag,
  UtensilsCrossed,
  Car,
  Zap,
  Fuel,
  Heart,
  GraduationCap,
  Home,
  Briefcase,
  Megaphone,
  Wrench,
  Monitor,
  Ban,
  Users,
  Scissors,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Check,
  X,
  CalendarClock,
  Receipt,
  ShieldCheck,
  Percent,
} from "lucide-react";
import { clsx } from 'clsx';

// ── Icon Map ──

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  UtensilsCrossed, Car, Zap, Fuel, Heart, GraduationCap, Home,
  Briefcase, Megaphone, Wrench, Monitor, Tag, Ban, Users, Scissors,
  Dumbbell: Heart, // fallback
};

// ── Helpers ──

const MONTH_NAMES_PT = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

function formatCurrency(value: string | number | null | undefined): string {
  if (value == null) return '€0,00';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '€0,00';
  return new Intl.NumberFormat('pt-PT', {
    style: 'currency',
    currency: 'EUR',
  }).format(num);
}

function getPeriodLabel(periodType: 'month' | 'quarter', year: number, periodValue: number): string {
  if (periodType === 'quarter') {
    return `T${periodValue} ${year}`;
  }
  return `${MONTH_NAMES_PT[periodValue - 1]} ${year}`;
}

/** Calculate the payment deadline date for a given period */
function getDeadlineDate(periodType: 'month' | 'quarter', year: number, periodValue: number): Date {
  if (periodType === 'quarter') {
    // Q1 → 20 May, Q2 → 20 Aug, Q3 → 20 Nov, Q4 → 20 Feb next year
    const deadlineMonth = [4, 7, 10, 1]; // 0-indexed months
    const deadlineYear = periodValue === 4 ? year + 1 : year;
    return new Date(deadlineYear, deadlineMonth[periodValue - 1], 20);
  }
  // Monthly: 20th of the next month
  const nextMonth = periodValue; // periodValue is 1-indexed, Date month is 0-indexed, so periodValue = next month's 0-index
  const deadlineYear = periodValue === 12 ? year + 1 : year;
  const monthIdx = periodValue === 12 ? 0 : nextMonth;
  return new Date(deadlineYear, monthIdx, 20);
}

function getDaysRemaining(deadline: Date): number {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const diff = deadline.getTime() - now.getTime();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

function formatDeadlineDatePT(date: Date): string {
  return `20 de ${MONTH_NAMES_PT[date.getMonth()]} de ${date.getFullYear()}`;
}

// ── Main Page Component ──

export default function SummaryPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  // Period navigation
  const [periodType, setPeriodType] = useState<"month" | "quarter">("quarter");
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [periodValue, setPeriodValue] = useState(() => {
    const now = new Date();
    return Math.ceil((now.getMonth() + 1) / 3); // current quarter
  });

  // VAT on sales editing
  const [isEditingVatSales, setIsEditingVatSales] = useState(false);
  const [vatSalesInput, setVatSalesInput] = useState("");
  const [isSavingVatSales, setIsSavingVatSales] = useState(false);
  const [vatSalesError, setVatSalesError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const params: Record<string, string | number> = {
        period_type: periodType,
        year,
      };
      if (periodType === "quarter") {
        params.quarter = periodValue;
      } else {
        params.month = periodValue;
      }
      const data = await api.getSummary(
        params as Parameters<typeof api.getSummary>[0],
      );
      setSummary(data);
    } catch (err) {
      setError("Não foi possível carregar o resumo");
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [periodType, year, periodValue]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  // ── Period Navigation ──

  const navigatePeriod = (direction: "prev" | "next") => {
    if (periodType === "quarter") {
      if (direction === "prev") {
        if (periodValue === 1) {
          setYear((y) => y - 1);
          setPeriodValue(4);
        } else {
          setPeriodValue((v) => v - 1);
        }
      } else {
        if (periodValue === 4) {
          setYear((y) => y + 1);
          setPeriodValue(1);
        } else {
          setPeriodValue((v) => v + 1);
        }
      }
    } else {
      if (direction === "prev") {
        if (periodValue === 1) {
          setYear((y) => y - 1);
          setPeriodValue(12);
        } else {
          setPeriodValue((v) => v - 1);
        }
      } else {
        if (periodValue === 12) {
          setYear((y) => y + 1);
          setPeriodValue(1);
        } else {
          setPeriodValue((v) => v + 1);
        }
      }
    }
  };

  const handleTogglePeriodType = (newType: "month" | "quarter") => {
    if (newType === periodType) return;
    setPeriodType(newType);
    if (newType === "quarter") {
      // Convert month to its quarter
      setPeriodValue(Math.ceil(periodValue / 3));
    } else {
      // Convert quarter to its first month
      setPeriodValue((periodValue - 1) * 3 + 1);
    }
  };

  // ── VAT on Sales Save ──

  const handleSaveVatSales = async () => {
    const amount = parseAmountInput(vatSalesInput);
    if (amount === null) {
      setVatSalesError("Introduza um valor como 1.234,56");
      return;
    }
    try {
      setIsSavingVatSales(true);
      setVatSalesError(null);
      await api.upsertVatSales({
        period_type: periodType,
        year,
        period_value: periodValue,
        vat_amount: amount,
      });
      setIsEditingVatSales(false);
      await fetchSummary();
    } catch (err) {
      console.error("Failed to save VAT on sales:", err);
      setVatSalesError("Não foi possível guardar. Tente novamente.");
    } finally {
      setIsSavingVatSales(false);
    }
  };

  // ── Derived values ──

  const hasVatOnSales = summary?.estimated_iva_payable != null;
  const ivaPayable = hasVatOnSales ? parseFloat(summary!.estimated_iva_payable!) : 0;
  const isRefund = ivaPayable < 0;

  const startEditingVatSales = () => {
    setVatSalesInput(
      summary?.vat_on_sales != null
        ? parseFloat(summary.vat_on_sales).toFixed(2).replace(".", ",")
        : "",
    );
    setVatSalesError(null);
    setIsEditingVatSales(true);
  };

  const deadline = useMemo(
    () => getDeadlineDate(periodType, year, periodValue),
    [periodType, year, periodValue],
  );
  const daysRemaining = useMemo(() => getDaysRemaining(deadline), [deadline]);

  const handleExport = async () => {
    try {
      setIsExporting(true);
      setExportError(null);
      const { blob, filename } = await api.downloadExport({
        period_type: periodType,
        year,
        ...(periodType === "quarter"
          ? { quarter: periodValue }
          : { month: periodValue }),
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export failed:", err);
      setExportError("Exportação falhou. Tente novamente.");
    } finally {
      setIsExporting(false);
    }
  };

  // ── Render ──

  return (
    <AppLayout title="Summary">
      <div className="p-4 space-y-4 pb-8">
        {/* ─── 1. Period Selector ─── */}
        <PeriodSelector
          periodType={periodType}
          year={year}
          periodValue={periodValue}
          onToggleType={handleTogglePeriodType}
          onNavigate={navigatePeriod}
        />

        {isLoading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorCard error={error} onRetry={fetchSummary} />
        ) : summary ? (
          <>
            {/* ─── 2. Main IVA Card (Hero) ─── */}
            <div className="card p-6 relative overflow-hidden">
              <div className="flex items-start justify-between mb-1">
                <span className="text-sm font-medium text-gray-500">
                  IVA estimado — {getPeriodLabel(periodType, year, periodValue)}
                </span>
                {hasVatOnSales &&
                  (isRefund ? (
                    <TrendingDown className="w-5 h-5 text-success-500" />
                  ) : (
                    <TrendingUp className="w-5 h-5 text-warning-500" />
                  ))}
              </div>
              {hasVatOnSales ? (
                <>
                  <div
                    className={clsx(
                      "text-4xl font-bold tracking-tight",
                      isRefund ? "text-emerald-600" : "text-gray-900",
                    )}
                  >
                    {formatCurrency(summary.estimated_iva_payable)}
                  </div>
                  <p className="text-sm text-gray-500 mt-1">
                    {isRefund ? "Reembolso estimado" : "Estimativa a pagar"}
                  </p>
                </>
              ) : (
                <>
                  <p className="text-lg font-semibold text-gray-900 mt-2">
                    Falta o IVA das vendas
                  </p>
                  <p className="text-sm text-gray-500 mt-1">
                    Sem ele não conseguimos estimar o IVA a pagar.
                  </p>
                  <button
                    type="button"
                    onClick={startEditingVatSales}
                    className="mt-3 text-sm font-medium text-blue-600 hover:text-blue-700"
                  >
                    Introduzir IVA das vendas
                  </button>
                </>
              )}

              {/* Confidence badge */}
              <div className="flex items-center gap-3 mt-4 pt-3 border-t border-gray-100">
                <ConfidenceBadge percent={summary.confidence_percent} />
                <span className="text-xs text-gray-500">
                  Baseado em {summary.ready_count} de {summary.total_documents}{" "}
                  documentos revistos
                </span>
              </div>
            </div>

            {/* ─── 3. IVA Breakdown Mini-table ─── */}
            <div className="card p-4 space-y-0 divide-y divide-gray-100">
              <div className="flex items-center justify-between py-2.5">
                <span className="text-sm text-gray-600">
                  IVA dedutível (compras)
                </span>
                <span className="text-sm font-semibold text-gray-900">
                  {formatCurrency(summary.deductible_vat)}
                </span>
              </div>
              {parseFloat(summary.deductible_vat_pending) > 0 && (
                <div className="flex items-center justify-between py-2.5">
                  <span className="text-sm text-gray-500">
                    Em recibos por rever (fora da estimativa)
                  </span>
                  <span className="text-sm text-gray-500">
                    {formatCurrency(summary.deductible_vat_pending)}
                  </span>
                </div>
              )}
              <div className="flex items-center justify-between py-2.5">
                <span className="text-sm text-gray-600">
                  IVA cobrado (vendas)
                </span>
                <div className="flex items-center gap-2">
                  {isEditingVatSales ? (
                    /* ─── 4. VAT on Sales Input ─── */
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm text-gray-400">€</span>
                      <input
                        type="text"
                        inputMode="decimal"
                        value={vatSalesInput}
                        onChange={(e) => setVatSalesInput(e.target.value)}
                        className="w-24 px-2 py-1 text-sm text-right border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        placeholder="0,00"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSaveVatSales();
                          if (e.key === "Escape") setIsEditingVatSales(false);
                        }}
                      />
                      <button
                        onClick={handleSaveVatSales}
                        disabled={isSavingVatSales}
                        className="p-1 rounded-md text-emerald-600 hover:bg-emerald-50 disabled:opacity-50"
                        aria-label="Guardar"
                      >
                        <Check className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setIsEditingVatSales(false)}
                        className="p-1 rounded-md text-gray-400 hover:bg-gray-100"
                        aria-label="Cancelar"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <span className="text-sm font-semibold text-gray-900">
                        {summary.vat_on_sales != null
                          ? formatCurrency(summary.vat_on_sales)
                          : "Por introduzir"}
                      </span>
                      <button
                        onClick={startEditingVatSales}
                        className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100"
                        aria-label="Editar IVA vendas"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="flex items-center justify-between py-2.5">
                <span className="text-sm font-semibold text-gray-900">
                  IVA a pagar / receber
                </span>
                <span
                  className={clsx(
                    "text-sm font-bold",
                    isRefund ? "text-emerald-600" : "text-gray-900",
                  )}
                >
                  {hasVatOnSales ? formatCurrency(summary.estimated_iva_payable) : "—"}
                </span>
              </div>
              {vatSalesError && (
                <p role="alert" className="py-2 text-sm text-red-600">
                  {vatSalesError}
                </p>
              )}
            </div>

            {/* ─── 5. Deadline Reminder ─── */}
            <div className="card p-4 flex items-center gap-3">
              <div
                className={clsx(
                  "w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0",
                  daysRemaining < 7
                    ? "bg-red-100"
                    : daysRemaining <= 14
                      ? "bg-amber-100"
                      : "bg-emerald-100",
                )}
              >
                <CalendarClock
                  className={clsx(
                    "w-5 h-5",
                    daysRemaining < 7
                      ? "text-red-600"
                      : daysRemaining <= 14
                        ? "text-amber-600"
                        : "text-emerald-600",
                  )}
                />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900">
                  Prazo de pagamento: {formatDeadlineDatePT(deadline)}
                </p>
                <p
                  className={clsx(
                    "text-xs font-medium mt-0.5",
                    daysRemaining < 7
                      ? "text-red-600"
                      : daysRemaining <= 14
                        ? "text-amber-600"
                        : "text-emerald-600",
                  )}
                >
                  {daysRemaining > 0
                    ? `Faltam ${daysRemaining} dias`
                    : daysRemaining === 0
                      ? "Hoje é o prazo!"
                      : `Atrasado ${Math.abs(daysRemaining)} dias`}
                </p>
              </div>
            </div>

            {/* ─── 6. Stats Grid (2x2) ─── */}
            <div className="grid grid-cols-2 gap-3">
              <StatCard
                icon={<Receipt className="w-4 h-4 text-blue-600" />}
                label="Recibos"
                value={String(summary.total_documents)}
                bgColor="bg-blue-50"
              />
              <StatCard
                icon={<Percent className="w-4 h-4 text-purple-600" />}
                label="IVA total"
                value={formatCurrency(summary.total_vat)}
                bgColor="bg-purple-50"
              />
              <StatCard
                icon={<ShieldCheck className="w-4 h-4 text-emerald-600" />}
                label="Dedutível"
                value={formatCurrency(summary.deductible_vat)}
                bgColor="bg-emerald-50"
              />
              <StatCard
                icon={<CheckCircle className="w-4 h-4 text-sky-600" />}
                label="Confiança"
                value={`${summary.confidence_percent}%`}
                bgColor="bg-sky-50"
              />
            </div>

            {/* ─── Document Status ─── */}
            <div className="card p-4">
              <h3 className="font-medium text-gray-900 mb-3">
                Estado dos documentos
              </h3>
              <div className="space-y-2">
                <StatusRow
                  icon={<CheckCircle className="w-4 h-4 text-success-500" />}
                  label="Prontos"
                  count={summary.ready_count}
                />
                <StatusRow
                  icon={<FileWarning className="w-4 h-4 text-warning-500" />}
                  label="Para revisão"
                  count={summary.needs_review_count}
                />
                <StatusRow
                  icon={<Clock className="w-4 h-4 text-gray-400" />}
                  label="Em processamento"
                  count={summary.processing_count}
                />
                {summary.failed_count > 0 && (
                  <StatusRow
                    icon={<AlertCircle className="w-4 h-4 text-red-500" />}
                    label="Falhados"
                    count={summary.failed_count}
                  />
                )}
              </div>
            </div>

            {/* ─── 7. Warnings Section ─── */}
            {summary.warnings.length > 0 && (
              <div className="card p-4 bg-amber-50 border-amber-200">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-amber-900">Atenção</h3>
                    <ul className="mt-1 text-sm text-amber-800 space-y-1">
                      {summary.warnings.map((warning, i) => (
                        <li key={i} className="flex items-start gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0 mt-1.5" />
                          <span>{warning}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* ─── 8. Category Breakdowns (enhanced) ─── */}
            {summary.expense_breakdown &&
              summary.expense_breakdown.length > 0 && (
                <CategoryBreakdownSection
                  title="Despesas por categoria"
                  items={summary.expense_breakdown}
                  totalGross={parseFloat(summary.total_gross) || 1}
                  type="expense"
                />
              )}

            {summary.irs_breakdown && summary.irs_breakdown.length > 0 && (
              <CategoryBreakdownSection
                title="Setores IRS"
                items={summary.irs_breakdown}
                totalGross={parseFloat(summary.total_gross) || 1}
                type="irs"
              />
            )}

            {/* ─── Export Error ─── */}
            {exportError && (
              <div className="card p-3 bg-red-50 border-red-200 flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
                <span className="text-sm text-red-800">{exportError}</span>
              </div>
            )}

            {/* ─── 9. Export Button ─── */}
            <div className="space-y-1.5">
              <button
                onClick={handleExport}
                disabled={isExporting || summary.total_documents === 0}
                className="btn-primary btn-lg w-full flex items-center justify-center gap-2"
              >
                <Download className="w-5 h-5" />
                {isExporting ? "A gerar..." : "Enviar ao Contabilista"}
              </button>
              <p className="text-xs text-center text-gray-400">
                Inclui {summary.total_documents} recibo
                {summary.total_documents !== 1 ? "s" : ""} · Período:{" "}
                {getPeriodLabel(periodType, year, periodValue)}
              </p>
            </div>
          </>
        ) : null}
      </div>
    </AppLayout>
  );
}

// ── Sub-components ──

function PeriodSelector({
  periodType,
  year,
  periodValue,
  onToggleType,
  onNavigate,
}: {
  periodType: 'month' | 'quarter';
  year: number;
  periodValue: number;
  onToggleType: (type: 'month' | 'quarter') => void;
  onNavigate: (direction: 'prev' | 'next') => void;
}) {
  return (
    <div className="space-y-3">
      {/* Period type toggle */}
      <div className="flex items-center justify-center">
        <div className="inline-flex bg-gray-100 rounded-lg p-0.5">
          <button
            onClick={() => onToggleType('month')}
            className={clsx(
              'px-4 py-1.5 text-sm font-medium rounded-md transition-colors',
              periodType === 'month'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            )}
          >
            Mês
          </button>
          <button
            onClick={() => onToggleType('quarter')}
            className={clsx(
              'px-4 py-1.5 text-sm font-medium rounded-md transition-colors',
              periodType === 'quarter'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            )}
          >
            Trimestre
          </button>
        </div>
      </div>

      {/* Period navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => onNavigate('prev')}
          className="p-2 rounded-lg hover:bg-gray-100 active:bg-gray-200 transition-colors touch-manipulation"
          aria-label="Período anterior"
        >
          <ChevronLeft className="w-5 h-5 text-gray-600" />
        </button>
        <span className="text-base font-semibold text-gray-900">
          {getPeriodLabel(periodType, year, periodValue)}
        </span>
        <button
          onClick={() => onNavigate('next')}
          className="p-2 rounded-lg hover:bg-gray-100 active:bg-gray-200 transition-colors touch-manipulation"
          aria-label="Próximo período"
        >
          <ChevronRight className="w-5 h-5 text-gray-600" />
        </button>
      </div>
    </div>
  );
}

function ConfidenceBadge({ percent }: { percent: number }) {
  const radius = 14;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percent / 100) * circumference;
  const color = percent >= 80 ? 'text-emerald-500' : percent >= 50 ? 'text-amber-500' : 'text-red-500';
  const strokeColor = percent >= 80 ? '#10b981' : percent >= 50 ? '#f59e0b' : '#ef4444';

  return (
    <div className="relative w-10 h-10 flex-shrink-0">
      <svg className="w-10 h-10 -rotate-90" viewBox="0 0 36 36">
        <circle
          cx="18"
          cy="18"
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth="3"
        />
        <circle
          cx="18"
          cy="18"
          r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth="3"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <span className={clsx('absolute inset-0 flex items-center justify-center text-[10px] font-bold', color)}>
        {percent}%
      </span>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  bgColor,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  bgColor: string;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-1.5">
        <div className={clsx('w-7 h-7 rounded-lg flex items-center justify-center', bgColor)}>
          {icon}
        </div>
        <p className="text-xs text-gray-500 font-medium">{label}</p>
      </div>
      <p className="text-xl font-semibold text-gray-900">{value}</p>
    </div>
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

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="card p-6 animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-1/3 mb-3" />
        <div className="h-10 bg-gray-200 rounded w-2/3 mb-2" />
        <div className="h-3 bg-gray-200 rounded w-1/4" />
      </div>
      <div className="card p-4 animate-pulse space-y-3">
        <div className="h-4 bg-gray-200 rounded w-full" />
        <div className="h-4 bg-gray-200 rounded w-full" />
        <div className="h-4 bg-gray-200 rounded w-full" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="card p-4 animate-pulse">
            <div className="h-3 bg-gray-200 rounded w-2/3 mb-2" />
            <div className="h-6 bg-gray-200 rounded w-1/2" />
          </div>
        ))}
      </div>
    </div>
  );
}

function ErrorCard({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="card p-6 text-center">
      <AlertCircle className="w-12 h-12 text-danger-500 mx-auto mb-3" />
      <p className="text-gray-600">{error}</p>
      <button onClick={onRetry} className="btn-secondary btn-md mt-4">
        Tentar novamente
      </button>
    </div>
  );
}

function DeductibleBadge({ pct }: { pct: number | undefined }) {
  if (pct == null) return null;
  return (
    <span
      className={clsx(
        "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold",
        pct === 100
          ? "bg-emerald-100 text-emerald-700"
          : pct > 0
            ? "bg-amber-100 text-amber-700"
            : "bg-gray-100 text-gray-500",
      )}
    >
      {pct}%
    </span>
  );
}

function CategoryBreakdownSection({
  title,
  items,
  totalGross,
  type,
}: {
  title: string;
  items: CategoryBreakdown[];
  totalGross: number;
  type: "expense" | "irs";
}) {
  const [expanded, setExpanded] = useState(false);
  const visibleItems = expanded ? items : items.slice(0, 4);

  return (
    <div className="card p-4">
      <h3 className="font-medium text-gray-900 mb-3">{title}</h3>
      <div className="space-y-2">
        {visibleItems.map((item) => {
          const info =
            type === "expense"
              ? getExpenseCategoryInfo(item.category)
              : getIrsSectorInfo(item.category);
          const IconComp = ICON_MAP[info.icon] || Tag;
          const total = parseFloat(item.total);
          const pct = totalGross > 0 ? (total / totalGross) * 100 : 0;
          const deductiblePct = item.deductible_pct ?? info.deductiblePct;

          return (
            <div key={item.category} className="flex items-center gap-3">
              <div
                className={clsx(
                  "w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0",
                  info.color,
                )}
              >
                <IconComp className={clsx("w-4 h-4", info.textColor)} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-1">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="text-sm text-gray-900 font-medium truncate">
                      {info.label}
                    </span>
                    {type === "expense" && (
                      <DeductibleBadge pct={deductiblePct} />
                    )}
                  </div>
                  <div className="flex flex-col items-end flex-shrink-0 ml-2">
                    <span className="text-sm font-semibold text-gray-900">
                      {formatCurrency(item.total)}
                    </span>
                    {item.deductible_vat && (
                      <span className="text-[10px] text-emerald-600 font-medium">
                        IVA ded. {formatCurrency(item.deductible_vat)}
                      </span>
                    )}
                  </div>
                </div>
                <div className="mt-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={clsx(
                      "h-full rounded-full",
                      info.color.replace("100", "400"),
                    )}
                    style={{ width: `${Math.min(pct, 100)}%` }}
                  />
                </div>
                <div className="flex items-center justify-between mt-0.5">
                  <span className="text-xs text-gray-500">
                    {item.count} recibo{item.count !== 1 ? "s" : ""}
                  </span>
                  <span className="text-xs text-gray-500">
                    {pct.toFixed(0)}%
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {items.length > 4 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full mt-3 flex items-center justify-center gap-1 text-sm text-gray-500 font-medium touch-manipulation py-1"
        >
          {expanded ? (
            <>
              Mostrar menos <ChevronUp className="w-4 h-4" />
            </>
          ) : (
            <>
              Mostrar todos ({items.length}) <ChevronDown className="w-4 h-4" />
            </>
          )}
        </button>
      )}
    </div>
  );
}
