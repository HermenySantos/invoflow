'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AppLayout } from '@/components/layout/AppLayout';
import { api, Document, AuditEntry, AuditTrailResponse } from '@/lib/api';
import { ImageViewer } from '@/components/review';
import { 
  getExpenseCategoryInfo,
  EXPENSE_CATEGORY_LIST,
  CategoryInfo,
} from '@/lib/categories';
import { 
  ArrowLeft, 
  AlertCircle, 
  AlertTriangle,
  CheckCircle,
  Trash2,
  Loader2,
  X,
  Edit3,
  Calendar,
  Building2,
  Receipt,
  Euro,
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
  ChevronDown,
  ChevronUp,
  Upload,
  Eye,
  Clock,
  Info,
} from 'lucide-react';
import Link from 'next/link';

// Portuguese VAT rates for auto-detection
const PT_VAT_RATES = [6, 13, 23, 0];

// Map icon name strings to Lucide components
const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  UtensilsCrossed, Car, Zap, Fuel, Heart, GraduationCap, Home,
  Briefcase, Megaphone, Wrench, Monitor, Tag,
};

// Audit trail action config
const AUDIT_ACTION_CONFIG: Record<string, { icon: React.ComponentType<{ className?: string }>; label: string }> = {
  create: { icon: Upload, label: 'Documento carregado' },
  ocr_extract: { icon: Eye, label: 'Dados extraídos por OCR' },
  auto_categorize: { icon: Tag, label: 'Categoria atribuída automaticamente' },
  update: { icon: Edit3, label: 'Editado pelo utilizador' },
  delete: { icon: Trash2, label: 'Documento eliminado' },
};

const AUDIT_SOURCE_BADGE: Record<string, { label: string; className: string }> = {
  ocr: { label: 'OCR', className: 'bg-blue-100 text-blue-700' },
  user: { label: 'Utilizador', className: 'bg-green-100 text-green-700' },
  system: { label: 'Sistema', className: 'bg-gray-100 text-gray-600' },
};

/** Relative timestamp in Portuguese */
function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffSec = Math.round((now - then) / 1000);
  if (diffSec < 60) return 'agora mesmo';
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `há ${diffMin} min`;
  const diffHours = Math.round(diffMin / 60);
  if (diffHours < 24) return `há ${diffHours} hora${diffHours > 1 ? 's' : ''}`;
  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 30) return `há ${diffDays} dia${diffDays > 1 ? 's' : ''}`;
  const diffMonths = Math.round(diffDays / 30);
  return `há ${diffMonths} ${diffMonths > 1 ? 'meses' : 'mês'}`;
}

export default function ReceiptDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [document, setDocument] = useState<Document | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Edit mode - only when user explicitly wants to edit
  const [isEditing, setIsEditing] = useState(false);
  const [editData, setEditData] = useState({
    vendor_name: '',
    document_date: '',
    gross_amount: '',
    vat_amount: '',
  });

  // Category picker
  const [showCategoryPicker, setShowCategoryPicker] = useState(false);
  const [isSavingCategory, setIsSavingCategory] = useState(false);

  // Audit trail
  const [auditTrail, setAuditTrail] = useState<AuditTrailResponse | null>(null);
  const [isAuditLoading, setIsAuditLoading] = useState(false);
  const [showAuditTrail, setShowAuditTrail] = useState(false);

  const fetchDocument = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await api.getDocument(params.id as string);
      setDocument(data);
      
      // Pre-fill edit form
      setEditData({
        vendor_name: data.vendor_name || '',
        document_date: data.document_date || '',
        gross_amount: data.gross_amount || '',
        vat_amount: data.vat_amount || '',
      });
    } catch (err) {
      setError('Não foi possível carregar o recibo.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDocument();
  }, [params.id]);

  // Fetch audit trail on mount
  useEffect(() => {
    const fetchAudit = async () => {
      try {
        setIsAuditLoading(true);
        const data = await api.getDocumentAuditTrail(params.id as string);
        setAuditTrail(data);
      } catch (err) {
        console.error('Failed to load audit trail:', err);
      } finally {
        setIsAuditLoading(false);
      }
    };
    fetchAudit();
  }, [params.id]);

  // Auto-detect VAT rate for display
  const getVatRateDisplay = useCallback(() => {
    if (!document) return null;
    
    // If we have vat_rate from backend, use it
    if (document.vat_rate) {
      return `${parseFloat(document.vat_rate).toFixed(0)}%`;
    }
    
    // Otherwise calculate from amounts
    const gross = parseFloat(document.gross_amount || '0');
    const vat = parseFloat(document.vat_amount || '0');
    if (gross > 0 && vat >= 0) {
      const net = gross - vat;
      if (net > 0) {
        const rate = (vat / net) * 100;
        const closest = PT_VAT_RATES.reduce((prev, curr) => 
          Math.abs(curr - rate) < Math.abs(prev - rate) ? curr : prev
        );
        if (Math.abs(rate - closest) < 3) {
          return `${closest}%`;
        }
      }
    }
    return null;
  }, [document]);

  // Check if all essential data is present
  const isComplete = useCallback(() => {
    if (!document) return false;
    return !!(
      document.vendor_name &&
      document.document_date &&
      document.gross_amount
    );
  }, [document]);

  // Confidence level
  const getConfidenceLevel = useCallback(() => {
    if (!document?.ocr_confidence) return 'unknown';
    const conf = parseFloat(document.ocr_confidence);
    if (conf >= 85) return 'high';
    if (conf >= 65) return 'medium';
    return 'low';
  }, [document]);

  const handleConfirm = async () => {
    if (!document) return;
    
    try {
      setIsSaving(true);
      setError(null);
      
      await api.updateDocument(document.id, { status: 'ready' });
      router.push('/receipts');
    } catch (err) {
      console.error('Failed to confirm:', err);
      setError('Não foi possível guardar. Tente novamente.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!document) return;
    
    try {
      setIsSaving(true);
      setError(null);
      
      await api.updateDocument(document.id, {
        vendor_name: editData.vendor_name || null,
        document_date: editData.document_date || null,
        gross_amount: editData.gross_amount || null,
        vat_amount: editData.vat_amount || null,
        status: 'ready',
      });
      router.push('/receipts');
    } catch (err) {
      console.error('Failed to save:', err);
      setError('Não foi possível guardar. Tente novamente.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteClick = () => setShowDeleteModal(true);
  const handleDeleteCancel = () => setShowDeleteModal(false);

  const handleDeleteConfirm = async () => {
    if (!document) return;
    
    try {
      setIsDeleting(true);
      await api.deleteDocument(document.id);
      setShowDeleteModal(false);
      router.push('/receipts');
    } catch (err) {
      console.error('Failed to delete:', err);
      setIsDeleting(false);
      setShowDeleteModal(false);
      setError('Não foi possível remover. Tente novamente.');
    }
  };

  const formatCurrency = (value: string | null) => {
    if (!value) return '—';
    const num = parseFloat(value);
    return isNaN(num)
      ? '—'
      : new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(num);
  };

  const formatDate = (value: string | null) => {
    if (!value) return '—';
    try {
      return new Date(value).toLocaleDateString('pt-PT', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      });
    } catch {
      return value;
    }
  };

  const handleCategoryChange = async (category: string) => {
    if (!document) return;
    setShowCategoryPicker(false);
    
    try {
      setIsSavingCategory(true);
      const updated = await api.updateDocument(document.id, {
        expense_category: category,
      } as Partial<Document>);
      setDocument(updated);
    } catch (err) {
      console.error('Failed to update category:', err);
      setError('Não foi possível mudar a categoria.');
    } finally {
      setIsSavingCategory(false);
    }
  };

  const handleDeductibleChange = async (value: string) => {
    if (!document) return;
    try {
      setIsSavingCategory(true);
      const updated = await api.updateDocument(document.id, {
        deductible_pct_override: value === '' ? null : Number(value),
      } as Partial<Document>);
      setDocument(updated);
    } catch (err) {
      console.error('Failed to update deductible %:', err);
      setError('Não foi possível guardar a % dedutível.');
    } finally {
      setIsSavingCategory(false);
    }
  };

  return (
    <AppLayout>
      {/* Header */}
      <header className="sticky top-0 z-40 bg-white border-b border-gray-200">
        <div className="flex items-center justify-between h-14 px-4">
          <Link href="/receipts" className="p-2 -ml-2 touch-manipulation">
            <ArrowLeft className="w-5 h-5 text-gray-600" />
          </Link>
          <h1 className="text-lg font-semibold text-gray-900">Recibo</h1>
          <button
            onClick={handleDeleteClick}
            disabled={isDeleting}
            aria-label="Remover recibo"
            className="p-2 -mr-2 text-danger-500 touch-manipulation disabled:opacity-50"
          >
            {isDeleting ? <Loader2 className="w-5 h-5 animate-spin" /> : <Trash2 className="w-5 h-5" />}
          </button>
        </div>
      </header>

      {/* Content */}
      <div className="p-4 space-y-4 max-w-lg mx-auto pb-56">
        {isLoading ? (
          <div className="space-y-4">
            <div className="card aspect-[4/3] animate-pulse bg-gray-200" />
            <div className="card p-4 space-y-3 animate-pulse">
              <div className="h-6 bg-gray-200 rounded w-2/3" />
              <div className="h-4 bg-gray-200 rounded w-1/3" />
              <div className="h-8 bg-gray-200 rounded w-1/2" />
            </div>
          </div>
        ) : error && !document ? (
          <div className="card p-6 text-center">
            <AlertCircle className="w-12 h-12 text-danger-500 mx-auto mb-3" />
            <p className="text-gray-600 mb-4">{error}</p>
            <button onClick={fetchDocument} className="btn-secondary btn-md">
              Tentar de novo
            </button>
          </div>
        ) : document ? (
          <>
            {/* Image preview */}
            <div className="card overflow-hidden">
              <ImageViewer
                src={document.file_url}
                alt={`Receipt from ${document.vendor_name || 'vendor'}`}
                mimeType={document.mime_type}
                filename={document.original_filename}
                className="aspect-[4/3] bg-gray-100"
              />
            </div>

            {/* Validation Warnings Banner */}
            {document.validation_warnings && document.validation_warnings.length > 0 && (
              <div className="space-y-2">
                {document.validation_warnings.map((w, i) => {
                  const severityStyles = {
                    error: 'bg-red-50 border-red-300 text-red-800',
                    warning: 'bg-amber-50 border-amber-300 text-amber-800',
                    info: 'bg-blue-50 border-blue-200 text-blue-700',
                  };
                  const severityIcons = {
                    error: <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />,
                    warning: <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />,
                    info: <Info className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />,
                  };
                  return (
                    <div
                      key={`${w.code}-${i}`}
                      className={`flex items-start gap-2 px-3 py-2.5 rounded-xl border ${severityStyles[w.severity]}`}
                    >
                      {severityIcons[w.severity]}
                      <span className="text-sm">{w.message}</span>
                    </div>
                  );
                })}
              </div>
            )}

            {isEditing ? (
              /* ========== EDIT MODE ========== */
              <div className="card p-4 space-y-4">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-semibold text-gray-900">Editar dados</h2>
                  <button 
                    onClick={() => setIsEditing(false)}
                    className="text-sm text-gray-500 touch-manipulation"
                  >
                    Cancelar
                  </button>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Fornecedor</label>
                  <input
                    type="text"
                    value={editData.vendor_name}
                    onChange={(e) => setEditData(d => ({ ...d, vendor_name: e.target.value }))}
                    placeholder="Who issued this receipt?"
                    className="input"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Data</label>
                  <input
                    type="date"
                    value={editData.document_date}
                    onChange={(e) => setEditData(d => ({ ...d, document_date: e.target.value }))}
                    max={new Date().toISOString().split('T')[0]}
                    className="input"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Total (€)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      inputMode="decimal"
                      value={editData.gross_amount}
                      onChange={(e) => setEditData(d => ({ ...d, gross_amount: e.target.value }))}
                      placeholder="0.00"
                      className="input"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">IVA (€)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      inputMode="decimal"
                      value={editData.vat_amount}
                      onChange={(e) => setEditData(d => ({ ...d, vat_amount: e.target.value }))}
                      placeholder="0.00"
                      className="input"
                    />
                  </div>
                </div>
              </div>
            ) : (
              /* ========== CONFIRMATION MODE (default) ========== */
              <>
                {/* Needs review alert */}
                {document.status === 'needs_review' && !isComplete() && (
                  <div className="card p-3 bg-amber-50 border-amber-200 flex items-start gap-2">
                    <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-amber-800">
                      Alguns dados não foram lidos. Toque em Editar dados para os preencher.
                    </p>
                  </div>
                )}

                {/* Extracted data summary */}
                <div className="card divide-y divide-gray-100">
                  {/* Vendor */}
                  <div className="p-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0">
                      <Building2 className="w-5 h-5 text-gray-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-500">Fornecedor</p>
                      <p className="font-semibold text-gray-900 truncate">
                        {document.vendor_name || <span className="text-gray-400">Não detetado</span>}
                      </p>
                    </div>
                  </div>

                  {/* Date */}
                  <div className="p-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0">
                      <Calendar className="w-5 h-5 text-gray-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-500">Data</p>
                      <p className="font-semibold text-gray-900">
                        {document.document_date ? formatDate(document.document_date) : <span className="text-gray-400">Não detetado</span>}
                      </p>
                    </div>
                  </div>

                  {/* Total Amount */}
                  <div className="p-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                      <Euro className="w-5 h-5 text-primary-600" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm text-gray-500">Total</p>
                      <p className="text-xl font-bold text-gray-900">
                        {document.gross_amount ? formatCurrency(document.gross_amount) : <span className="text-gray-400">—</span>}
                      </p>
                    </div>
                    {/* VAT breakdown */}
                    {document.vat_amount && (
                      <div className="text-right">
                        <p className="text-xs text-gray-500">VAT {getVatRateDisplay()}</p>
                        <p className="text-sm font-medium text-gray-700">
                          {formatCurrency(document.vat_amount)}
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Category chip */}
                {(() => {
                  const catInfo = getExpenseCategoryInfo(document.expense_category);
                  const IconComp = ICON_MAP[catInfo.icon] || Tag;
                  return (
                    <button
                      onClick={() => setShowCategoryPicker(true)}
                      disabled={isSavingCategory}
                      className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl ${catInfo.color} touch-manipulation transition-colors active:opacity-80`}
                    >
                      <IconComp className={`w-5 h-5 ${catInfo.textColor} flex-shrink-0`} />
                      <span className={`font-medium ${catInfo.textColor} flex-1 text-left`}>
                        {catInfo.label}
                      </span>
                      {isSavingCategory ? (
                        <Loader2 className={`w-4 h-4 ${catInfo.textColor} animate-spin`} />
                      ) : (
                        <ChevronDown className={`w-4 h-4 ${catInfo.textColor}`} />
                      )}
                    </button>
                  );
                })()}

                {/* VAT deductible % (CIVA art. 21) */}
                <label className="flex items-center justify-between gap-3 px-1 text-sm text-gray-600">
                  <span>IVA dedutível</span>
                  <select
                    value={document.deductible_pct_override ?? ''}
                    onChange={(e) => handleDeductibleChange(e.target.value)}
                    disabled={isSavingCategory}
                    className="input w-auto py-1.5"
                  >
                    <option value="">
                      Regra da categoria
                      {document.deductible_pct_override == null ? ` (${document.deductible_pct}%)` : ''}
                    </option>
                    <option value="100">100%</option>
                    <option value="50">50% (gasóleo, GPL)</option>
                    <option value="25">25%</option>
                    <option value="0">0% (gasolina, viatura ligeira)</option>
                  </select>
                </label>

                {/* Confidence indicator */}
                {document.ocr_confidence && (
                  <div className="flex items-center justify-between px-1">
                    <span className="text-xs text-gray-500">
                      Lido automaticamente
                    </span>
                    <span className={`text-xs font-medium ${
                      getConfidenceLevel() === 'high' ? 'text-green-600' :
                      getConfidenceLevel() === 'medium' ? 'text-amber-600' : 'text-red-600'
                    }`}>
                      {parseFloat(document.ocr_confidence).toFixed(0)}% de confiança
                    </span>
                  </div>
                )}

                {/* Edit button */}
                <button
                  onClick={() => setIsEditing(true)}
                  className="w-full py-3 flex items-center justify-center gap-2 text-gray-600 font-medium touch-manipulation"
                >
                  <Edit3 className="w-4 h-4" />
                  Editar dados
                </button>
              </>
            )}

            {/* Audit Trail Section */}
            <div className="mt-2">
              <button
                onClick={() => setShowAuditTrail(!showAuditTrail)}
                className="w-full flex items-center justify-between px-4 py-3 rounded-xl bg-gray-50 text-gray-700 font-medium touch-manipulation transition-colors active:bg-gray-100"
              >
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-gray-500" />
                  <span className="text-sm">
                    Histórico{auditTrail ? ` (${auditTrail.total})` : ''}
                  </span>
                </div>
                {showAuditTrail ? (
                  <ChevronUp className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                )}
              </button>

              {showAuditTrail && (
                <div className="mt-2 card p-4">
                  {isAuditLoading ? (
                    <div className="flex items-center justify-center py-4">
                      <Loader2 className="w-5 h-5 text-gray-400 animate-spin" />
                    </div>
                  ) : auditTrail && auditTrail.entries.length > 0 ? (
                    <div className="relative">
                      {/* Timeline line */}
                      <div className="absolute left-[15px] top-2 bottom-2 w-px bg-gray-200" />

                      <ul className="space-y-4 list-none p-0 m-0">
                        {auditTrail.entries.map((entry) => {
                          const config = AUDIT_ACTION_CONFIG[entry.action] || {
                            icon: Clock,
                            label: entry.action,
                          };
                          const ActionIcon = config.icon;
                          const sourceBadge = AUDIT_SOURCE_BADGE[entry.source] || AUDIT_SOURCE_BADGE.system;

                          // Parse changes
                          let changes: Record<string, { old: unknown; new: unknown }> | null = null;
                          if (entry.changes_json) {
                            try {
                              changes = JSON.parse(entry.changes_json);
                            } catch {
                              // ignore
                            }
                          }

                          return (
                            <li key={entry.id} className="relative flex gap-3 pl-0">
                              {/* Timeline dot / icon */}
                              <div className="relative z-10 w-[30px] h-[30px] rounded-full bg-white border border-gray-200 flex items-center justify-center flex-shrink-0">
                                <ActionIcon className="w-3.5 h-3.5 text-gray-500" />
                              </div>

                              {/* Content */}
                              <div className="flex-1 min-w-0 pt-0.5">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-sm font-medium text-gray-900">
                                    {config.label}
                                  </span>
                                  <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold ${sourceBadge.className}`}>
                                    {sourceBadge.label}
                                  </span>
                                </div>

                                {/* Changed fields */}
                                {changes && Object.keys(changes).length > 0 && (
                                  <div className="mt-1 space-y-0.5">
                                    {Object.entries(changes).map(([field, vals]) => (
                                      <p key={field} className="text-xs text-gray-500">
                                        <span className="font-medium">{field}:</span>{' '}
                                        <span className="text-gray-400">{String(vals.old ?? '—')}</span>
                                        {' → '}
                                        <span className="text-gray-700">{String(vals.new ?? '—')}</span>
                                      </p>
                                    ))}
                                  </div>
                                )}

                                <p className="text-xs text-gray-400 mt-0.5">
                                  {relativeTime(entry.created_at)}
                                </p>
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400 text-center py-3">
                      Sem histórico disponível
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Error message */}
            {error && (
              <div className="card p-3 bg-red-50 border-red-200 flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
                <span className="text-sm text-red-800">{error}</span>
              </div>
            )}
          </>
        ) : null}
      </div>

      {/* Fixed bottom action */}
      {document && !isLoading && (
        <div className="fixed bottom-16 left-0 right-0 p-4 bg-white border-t border-gray-200 safe-area-inset-bottom z-40">
          <div className="max-w-lg mx-auto">
            {/* Keep the amounts in view next to the action that confirms them */}
            {!isEditing && (
              <dl className="flex justify-between text-sm mb-3" aria-label="Valores do recibo">
                <div className="flex gap-1.5">
                  <dt className="text-gray-500">Total</dt>
                  <dd className="font-semibold text-gray-900">{formatCurrency(document.gross_amount)}</dd>
                </div>
                <div className="flex gap-1.5">
                  <dt className="text-gray-500">IVA</dt>
                  <dd className="font-semibold text-gray-900">{formatCurrency(document.vat_amount)}</dd>
                </div>
              </dl>
            )}
            {isEditing ? (
              <button
                onClick={handleSaveEdit}
                disabled={isSaving}
                className="btn-primary btn-lg w-full flex items-center justify-center gap-2"
              >
                {isSaving ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    A guardar...
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-5 h-5" />
                    Guardar e confirmar
                  </>
                )}
              </button>
            ) : (
              <button
                onClick={handleConfirm}
                disabled={isSaving}
                className="btn-primary btn-lg w-full flex items-center justify-center gap-2"
              >
                {isSaving ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    A guardar...
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-5 h-5" />
                    Está correto
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Category Picker Bottom Sheet */}
      {showCategoryPicker && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50" onClick={() => setShowCategoryPicker(false)}>
          <div 
            className="bg-white rounded-t-2xl shadow-xl w-full max-w-lg animate-in slide-in-from-bottom duration-200 max-h-[70vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-gray-100">
              <h2 className="text-lg font-semibold text-gray-900">Categoria</h2>
              <button onClick={() => setShowCategoryPicker(false)} className="p-1 text-gray-400 touch-manipulation">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="overflow-y-auto p-2">
              {EXPENSE_CATEGORY_LIST.map((cat) => {
                const IconComp = ICON_MAP[cat.icon] || Tag;
                const isSelected = document?.expense_category === cat.key;
                return (
                  <button
                    key={cat.key}
                    onClick={() => handleCategoryChange(cat.key)}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl touch-manipulation transition-colors ${
                      isSelected ? `${cat.color} ring-2 ring-primary-300` : 'hover:bg-gray-50 active:bg-gray-100'
                    }`}
                  >
                    <div className={`w-9 h-9 rounded-lg ${cat.color} flex items-center justify-center flex-shrink-0`}>
                      <IconComp className={`w-5 h-5 ${cat.textColor}`} />
                    </div>
                    <span className={`font-medium ${isSelected ? cat.textColor : 'text-gray-900'} flex-1 text-left`}>
                      {cat.label}
                    </span>
                    {isSelected && (
                      <CheckCircle className="w-5 h-5 text-primary-500 flex-shrink-0" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Delete Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/50">
          <div className="bg-white rounded-t-2xl sm:rounded-2xl shadow-xl w-full max-w-sm p-6 animate-in slide-in-from-bottom sm:zoom-in duration-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">Remover recibo</h2>
              <button onClick={handleDeleteCancel} className="p-1 text-gray-400 touch-manipulation">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <p className="text-gray-600 mb-6">
              O recibo deixa de aparecer na lista, no resumo e na exportação. O original
              fica guardado, como a lei exige para faturas.
            </p>
            
            <div className="flex gap-3">
              <button
                onClick={handleDeleteCancel}
                disabled={isDeleting}
                className="flex-1 btn-secondary btn-md"
              >
                Cancelar
              </button>
              <button
                onClick={handleDeleteConfirm}
                disabled={isDeleting}
                className="flex-1 px-4 py-2.5 bg-red-500 text-white rounded-xl font-medium disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                Remover
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
