'use client';

import { useState, useEffect, useCallback } from "react";
import { AppLayout } from '@/components/layout/AppLayout';
import { api, Document } from '@/lib/api';
import {
  getExpenseCategoryInfo,
  EXPENSE_CATEGORY_LIST,
} from "@/lib/categories";
import {
  Receipt,
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Clock,
  XCircle,
  ChevronRight,
  RefreshCw,
  Search,
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
} from "lucide-react";
import { clsx } from 'clsx';
import Link from 'next/link';

// Map icon name strings to Lucide components
const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  UtensilsCrossed, Car, Zap, Fuel, Heart, GraduationCap, Home,
  Briefcase, Megaphone, Wrench, Monitor, Tag,
};

export default function ReceiptsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const hasFilters = Boolean(activeCategory || search || dateFrom || dateTo);

  // Search after the user pauses typing, not on every key.
  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const fetchDocuments = useCallback(async (category?: string | null) => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await api.getDocuments({
        page_size: 50,
        expense_category: category || undefined,
        q: search || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      });
      setDocuments(data.documents);
    } catch (err) {
      setError("Failed to load receipts");
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [search, dateFrom, dateTo]);

  useEffect(() => {
    fetchDocuments(activeCategory);
  }, [activeCategory, fetchDocuments]);

  const handleCategoryFilter = (key: string | null) => {
    setActiveCategory(key);
  };

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

  const getStatusInfo = (
    status: Document["status"],
  ): { icon: React.ReactNode; label: string } => {
    switch (status) {
      case "ready":
        return {
          icon: (
            <CheckCircle
              className="w-4 h-4 text-success-500"
              aria-hidden="true"
            />
          ),
          label: "Ready",
        };
      case "needs_review":
        return {
          icon: (
            <AlertCircle
              className="w-4 h-4 text-warning-500"
              aria-hidden="true"
            />
          ),
          label: "Needs review",
        };
      case "processing":
      case "pending":
        return {
          icon: (
            <Clock
              className="w-4 h-4 text-gray-400 animate-pulse"
              aria-hidden="true"
            />
          ),
          label: "Processing",
        };
      case "failed":
        return {
          icon: (
            <XCircle className="w-4 h-4 text-danger-500" aria-hidden="true" />
          ),
          label: "Failed",
        };
      default:
        return { icon: null, label: "Unknown" };
    }
  };

  return (
    <AppLayout title="Recibos">
      <section className="p-4" aria-label="Receipts list">
        <div className="mb-3 space-y-2">
          <label className="relative block">
            <span className="sr-only">Procurar recibos</span>
            <Search
              className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2"
              aria-hidden="true"
            />
            <input
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Fornecedor, NIF ou nº da fatura"
              className="input pl-9"
            />
          </label>
          <div className="flex gap-2">
            <label className="flex-1 text-xs text-gray-500">
              De
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="input mt-1"
              />
            </label>
            <label className="flex-1 text-xs text-gray-500">
              Até
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="input mt-1"
              />
            </label>
          </div>
        </div>
        {isLoading ? (
          <div
            className="space-y-3"
            role="status"
            aria-label="Loading receipts"
          >
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="card p-4 animate-pulse"
                aria-hidden="true"
              >
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-gray-200 rounded-lg" />
                  <div className="flex-1">
                    <div className="h-4 bg-gray-200 rounded w-1/2 mb-2" />
                    <div className="h-3 bg-gray-200 rounded w-1/3" />
                  </div>
                </div>
              </div>
            ))}
            <span className="sr-only">Loading receipts...</span>
          </div>
        ) : error ? (
          <div className="card p-6 text-center" role="alert">
            <AlertCircle
              className="w-12 h-12 text-danger-500 mx-auto mb-3"
              aria-hidden="true"
            />
            <p className="text-gray-600">{error}</p>
            <button
              onClick={() => fetchDocuments(activeCategory)}
              className="btn-secondary btn-md mt-4"
              aria-label="Retry loading receipts"
            >
              Retry
            </button>
          </div>
        ) : documents.length === 0 && !hasFilters ? (
          <div className="card p-8 text-center">
            <Receipt
              className="w-16 h-16 text-gray-300 mx-auto mb-4"
              aria-hidden="true"
            />
            <h2 className="text-lg font-medium text-gray-900 mb-1">
              Ainda sem recibos
            </h2>
            <p className="text-gray-500 mb-4">
              Carregue um PDF ou uma foto para estimar o IVA
            </p>
            <Link href="/upload" className="btn-primary btn-md">
              Carregar recibo
            </Link>
          </div>
        ) : (
          <>
            {/* Category filter chips */}
            <div className="flex gap-2 overflow-x-auto pb-2 -mx-4 px-4 scrollbar-hide mb-1">
              <button
                onClick={() => handleCategoryFilter(null)}
                className={clsx(
                  "flex-shrink-0 px-3 py-1.5 rounded-full text-sm font-medium transition-colors touch-manipulation",
                  activeCategory === null
                    ? "bg-gray-900 text-white"
                    : "bg-gray-100 text-gray-600",
                )}
              >
                All
              </button>
              {EXPENSE_CATEGORY_LIST.map((cat) => {
                const IconComp = ICON_MAP[cat.icon] || Tag;
                const isActive = activeCategory === cat.key;
                return (
                  <button
                    key={cat.key}
                    onClick={() => handleCategoryFilter(cat.key)}
                    className={clsx(
                      "flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-colors touch-manipulation",
                      isActive
                        ? `${cat.color} ${cat.textColor} ring-1 ring-current`
                        : "bg-gray-100 text-gray-600",
                    )}
                  >
                    <IconComp className="w-3.5 h-3.5" aria-hidden="true" />
                    {cat.label}
                  </button>
                );
              })}
            </div>

            {/* Refresh button */}
            <div className="flex justify-end mb-3">
              <button
                onClick={() => fetchDocuments(activeCategory)}
                className="btn-secondary btn-sm flex items-center gap-1"
                aria-label="Refresh receipts list"
              >
                <RefreshCw className="w-4 h-4" aria-hidden="true" />
                Refresh
              </button>
            </div>

            {/* Empty filtered state */}
            {documents.length === 0 && hasFilters ? (
              <div className="card p-6 text-center">
                <Receipt
                  className="w-12 h-12 text-gray-300 mx-auto mb-3"
                  aria-hidden="true"
                />
                <p className="text-gray-500">Nenhum recibo corresponde aos filtros</p>
                <button
                  onClick={() => {
                    handleCategoryFilter(null);
                    setSearchInput("");
                    setDateFrom("");
                    setDateTo("");
                  }}
                  className="btn-secondary btn-sm mt-3"
                >
                  Limpar filtros
                </button>
              </div>
            ) : null}

            {/* Document list */}
            <ul
              className="space-y-2 list-none p-0 m-0"
              role="list"
              aria-label="Your receipts"
            >
              {documents.map((doc) => {
                const statusInfo = getStatusInfo(doc.status);
                const vendorName =
                  doc.vendor_name || "Fornecedor por preencher";
                const date = formatDate(doc.document_date || doc.created_at);
                const amount = formatCurrency(doc.gross_amount);
                const catInfo = getExpenseCategoryInfo(doc.expense_category);
                const CatIcon = ICON_MAP[catInfo.icon] || Tag;
                const hasError = doc.validation_warnings?.some(
                  (w) => w.severity === "error",
                );
                const hasWarning =
                  !hasError &&
                  doc.validation_warnings?.some(
                    (w) => w.severity === "warning",
                  );

                return (
                  <li key={doc.id}>
                    <Link
                      href={`/receipts/${doc.id}`}
                      className="card p-4 flex items-center gap-3 hover:bg-gray-50 transition-colors"
                      aria-label={`${vendorName}, ${date}, ${amount}, ${catInfo.label}, Status: ${statusInfo.label}`}
                    >
                      {/* Category icon */}
                      <div
                        className={`w-10 h-10 rounded-lg ${catInfo.color} flex items-center justify-center flex-shrink-0`}
                        aria-hidden="true"
                      >
                        <CatIcon className={`w-5 h-5 ${catInfo.textColor}`} />
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900 truncate">
                            {vendorName}
                          </span>
                          {statusInfo.icon}
                          <span className="sr-only">{statusInfo.label}</span>
                          {hasError && (
                            <AlertTriangle
                              className="w-4 h-4 text-red-500 flex-shrink-0"
                              aria-label="Erro de validação"
                            />
                          )}
                          {hasWarning && (
                            <AlertTriangle
                              className="w-4 h-4 text-amber-500 flex-shrink-0"
                              aria-label="Aviso de validação"
                            />
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-sm text-gray-500">
                          <span>{date}</span>
                          <span aria-hidden="true">·</span>
                          <span className="font-medium text-gray-700">
                            {amount}
                          </span>
                          <span aria-hidden="true">·</span>
                          <span className={`${catInfo.textColor} text-xs`}>
                            {catInfo.label}
                          </span>
                        </div>
                      </div>

                      <ChevronRight
                        className="w-5 h-5 text-gray-400"
                        aria-hidden="true"
                      />
                    </Link>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </section>
    </AppLayout>
  );
}
