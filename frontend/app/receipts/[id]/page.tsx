'use client';

import { useState, useEffect, useCallback, useRef, type CSSProperties } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AppLayout } from '@/components/layout/AppLayout';
import { ModalLayer } from '@/components/layout/ModalLayer';
import { api, Document, AuditEntry, AuditTrailResponse } from '@/lib/api';
import { DOCUMENT_TYPE_OPTIONS, PRINTED_PAIR_LABEL, SERIES_MISMATCH_DETAIL, SERIES_OVERRIDE_WARNING, documentTypeLabel, initialReviewEdit, isConcreteDocumentType, linkedRetypeBlocked, saveEditPayload, seriesBlocks, seriesOverrideAllowed } from '@/lib/reviewEdit';
import { ImageViewer } from '@/components/review';
import { PtDateInput } from '@/components/forms/PtDateInput';
import { saveErrorMessage } from '@/lib/saveError';
import { rateLimitWait, useRetryCountdown } from '@/lib/rateLimit';
import { softDisabled } from '@/lib/softDisabled';
import { RateLimitNotice } from '@/components/RateLimitNotice';
import { RateLimitButtonText } from '@/components/RateLimitButtonText';
import { requestScrollRestore } from '@/lib/mainScroll';
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
  /* After a save or delete, back on the list where the user left it, as with the back button */
  const backToList = () => {
    requestScrollRestore('/receipts');
    router.push('/receipts');
  };
  const [document, setDocument] = useState<Document | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  /* Set before the first await, so a double tap sends one DELETE even before isDeleting re-renders */
  const deletingRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const saveWait = useRetryCountdown();
  const showSaveError = (err: unknown) => {
    const wait = rateLimitWait(err);
    if (wait !== null) {
      setError(null);
      saveWait.start(wait, saveErrorMessage(err));
      return;
    }
    setError(saveErrorMessage(err));
  };
  
  // Edit mode - only when user explicitly wants to edit
  const [isEditing, setIsEditing] = useState(false);
  const editDateValidRef = useRef(true);
  const [editData, setEditData] = useState({
    vendor_name: '',
    document_date: '',
    gross_amount: '',
    vat_amount: '',
    document_type: 'unclassified',
    invoice_number: '',
  });
  // Non-QR rows open on Por classificar. A suggestion is read-only text, not the value.
  const [confirmType, setConfirmType] = useState('unclassified');
  const [acceptSeriesMismatch, setAcceptSeriesMismatch] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const loadSeq = useRef(0);
  const actionBarRef = useRef<HTMLDivElement>(null);
  const saveErrorRef = useRef<HTMLDivElement>(null);
  /* width / height of the loaded file; a ratio for another file_url is ignored, so the frame stays 3/4 */
  const [imageBox, setImageBox] = useState<{ url: string; ratio: number } | null>(null);
  const fileUrl = document?.file_url ?? null;
  const reportImageSize = useCallback((width: number, height: number) => {
    if (!fileUrl || width <= 0 || height <= 0) return;
    const ratio = width / height;
    setImageBox((prev) => (prev && prev.url === fileUrl && Math.abs(prev.ratio - ratio) < 1e-4 ? prev : { url: fileUrl, ratio }));
  }, [fileUrl]);

  // Category picker
  const [showCategoryPicker, setShowCategoryPicker] = useState(false);
  const [isSavingCategory, setIsSavingCategory] = useState(false);

  // Audit trail
  const [auditTrail, setAuditTrail] = useState<AuditTrailResponse | null>(null);
  const [isAuditLoading, setIsAuditLoading] = useState(false);
  const [showAuditTrail, setShowAuditTrail] = useState(false);

  const routeId = String(params.id ?? '');
  const [trackedId, setTrackedId] = useState(routeId);
  if (trackedId !== routeId) {
    setTrackedId(routeId);
    setDocument(null);
    setIsEditing(false);
    setConfirmType('unclassified');
    setAcceptSeriesMismatch(false);
    setIsLoading(true);
    setError(null);
    setAuditTrail(null);
  }

  // Ignore a response that belongs to a previous id. A failed load leaves no receipt to confirm.
  useEffect(() => {
    const seq = ++loadSeq.current;
    const requestedId = routeId;
    setDocument(null);
    setIsEditing(false);
    setConfirmType('unclassified');
    setAcceptSeriesMismatch(false);
    setEditData({
      vendor_name: '',
      document_date: '',
      gross_amount: '',
      vat_amount: '',
      document_type: 'unclassified',
      invoice_number: '',
    });
    setAuditTrail(null);
    setIsLoading(true);
    setError(null);

    let cancelled = false;
    (async () => {
      try {
        const data = await api.getDocument(requestedId);
        if (cancelled || seq !== loadSeq.current) return;
        if (data.id !== requestedId) {
          setDocument(null);
          setError('Não foi possível carregar o recibo.');
          return;
        }
        setDocument(data);
        setEditData(initialReviewEdit(data));
        setConfirmType(isConcreteDocumentType(data.document_type) ? data.document_type! : 'unclassified');
      } catch (err) {
        if (cancelled || seq !== loadSeq.current) return;
        setDocument(null);
        setError('Não foi possível carregar o recibo.');
        console.error(err);
      } finally {
        if (!cancelled && seq === loadSeq.current) setIsLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [routeId, reloadKey]);

  useEffect(() => {
    setAcceptSeriesMismatch(false);
  }, [editData.document_type, editData.invoice_number, confirmType, document?.invoice_number, document?.document_type]);

  // The receipt is still being read in the background: poll until it settles.
  const isProcessing = document?.status === 'processing';
  useEffect(() => {
    if (!isProcessing) return;
    const seq = loadSeq.current;
    const requestedId = routeId;
    const timer = setInterval(async () => {
      try {
        const data = await api.getDocument(requestedId);
        if (seq !== loadSeq.current || data.id !== requestedId) return;
        if (data.status === 'processing') return;
        setDocument(data);
        setEditData(initialReviewEdit(data));
        setConfirmType(isConcreteDocumentType(data.document_type) ? data.document_type! : 'unclassified');
      } catch {
        // Next tick retries.
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [isProcessing, routeId]);

  // Fetch audit trail for the receipt currently on screen.
  useEffect(() => {
    const seq = loadSeq.current;
    const requestedId = routeId;
    let cancelled = false;
    const fetchAudit = async () => {
      try {
        setIsAuditLoading(true);
        const data = await api.getDocumentAuditTrail(requestedId);
        if (cancelled || seq !== loadSeq.current) return;
        setAuditTrail(data);
      } catch (err) {
        if (cancelled || seq !== loadSeq.current) return;
        console.error('Failed to load audit trail:', err);
      } finally {
        if (!cancelled && seq === loadSeq.current) setIsAuditLoading(false);
      }
    };
    fetchAudit();
    return () => {
      cancelled = true;
    };
  }, [routeId]);

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
    if (!document || document.id !== routeId) return;
    const chosen = isConcreteDocumentType(document.document_type)
      ? document.document_type!
      : confirmType;
    if (!isConcreteDocumentType(chosen)) return;
    const mismatch =
      seriesBlocks(chosen, document.invoice_number, document.at_document_type, document.at_invoice_number) ||
      linkedRetypeBlocked(document.linked_at_pair, document.document_type, chosen);
    const canOverride = seriesOverrideAllowed(
      chosen,
      document.invoice_number,
      document.at_document_type,
      document.at_invoice_number,
    );
    if (mismatch && (!canOverride || !acceptSeriesMismatch)) {
      setError(SERIES_MISMATCH_DETAIL);
      return;
    }
    const payload = isConcreteDocumentType(document.document_type)
      ? { status: 'ready' as const }
      : { document_type: chosen, status: 'ready' as const };
    const confirmed = mismatch && canOverride ? { ...payload, accept_series_mismatch: true } : payload;
    
    try {
      setIsSaving(true);
      setError(null);
      
      await api.updateDocument(document.id, confirmed);
      backToList();
    } catch (err) {
      console.error('Failed to confirm:', err);
      showSaveError(err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!document || document.id !== routeId) return;
    // The date field shows its own error; do not send the last valid date as if it were the typed one.
    if (!editDateValidRef.current) return;
    const mismatch =
      seriesBlocks(
        editData.document_type,
        editData.invoice_number,
        document.at_document_type,
        document.at_invoice_number,
      ) || linkedRetypeBlocked(document.linked_at_pair, document.document_type, editData.document_type);
    const canOverride = seriesOverrideAllowed(
      editData.document_type,
      editData.invoice_number,
      document.at_document_type,
      document.at_invoice_number,
    );
    if (mismatch && (!canOverride || !acceptSeriesMismatch)) {
      setError(SERIES_MISMATCH_DETAIL);
      return;
    }
    
    try {
      setIsSaving(true);
      setError(null);
      
      await api.updateDocument(document.id, saveEditPayload(editData, mismatch && canOverride));
      backToList();
    } catch (err) {
      console.error('Failed to save:', err);
      showSaveError(err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteClick = () => {
    setDeleteError(null);
    setShowDeleteModal(true);
  };
  const handleDeleteCancel = () => {
    if (!deletingRef.current) setShowDeleteModal(false);
  };

  const handleDeleteConfirm = async () => {
    if (!document || deletingRef.current) return;
    deletingRef.current = true;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteDocument(document.id);
      setShowDeleteModal(false);
      backToList();
    } catch (err) {
      console.error('Failed to delete:', err);
      setDeleteError('Não foi possível remover. Tente novamente.');
    } finally {
      deletingRef.current = false;
      setIsDeleting(false);
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

  const editIsConcrete = isConcreteDocumentType(editData.document_type);
  const editSeriesMismatch =
    seriesBlocks(
      editData.document_type,
      editData.invoice_number,
      document?.at_document_type,
      document?.at_invoice_number,
    ) || linkedRetypeBlocked(document?.linked_at_pair, document?.document_type, editData.document_type);
  const editCanOverride = seriesOverrideAllowed(
    editData.document_type,
    editData.invoice_number,
    document?.at_document_type,
    document?.at_invoice_number,
  );
  const confirmChosen =
    document && isConcreteDocumentType(document.document_type)
      ? document.document_type!
      : confirmType;
  const confirmSeriesMismatch =
    !!document &&
    (seriesBlocks(
      confirmChosen,
      document.invoice_number,
      document.at_document_type,
      document.at_invoice_number,
    ) ||
      linkedRetypeBlocked(document.linked_at_pair, document.document_type, confirmChosen));
  const confirmCanOverride =
    !!document &&
    seriesOverrideAllowed(
      confirmChosen,
      document.invoice_number,
      document.at_document_type,
      document.at_invoice_number,
    );
  const detailColumns = !!document && !isLoading;
  /* The skeleton uses the same tracks, so the form does not jump when the receipt arrives. */
  const desktopColumns = isLoading || detailColumns;
  const imageAspect = imageBox && imageBox.url === fileUrl ? imageBox.ratio : null;
  const barMounted = !!document && !isLoading;

  useEffect(() => {
    if (!barMounted) return;
    const bar = actionBarRef.current;
    const main = window.document.getElementById('main-content');
    if (!bar || !main) return;
    const apply = (height: number) => {
      main.style.setProperty('--receipt-bar-h', `${Math.ceil(height)}px`);
    };
    apply(bar.getBoundingClientRect().height);
    if (typeof ResizeObserver === 'undefined') {
      return () => {
        main.style.removeProperty('--receipt-bar-h');
      };
    }
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.borderBoxSize?.[0]?.blockSize;
      apply(typeof box === 'number' && box > 0 ? box : bar.getBoundingClientRect().height);
    });
    observer.observe(bar);
    return () => {
      observer.disconnect();
      main.style.removeProperty('--receipt-bar-h');
    };
  }, [barMounted]);

  /* A capped bar scrolls to keep the focused button in view, which hides a new 409/503.
     Disabling that button drops focus to the body, so the error itself takes it. */
  useEffect(() => {
    if (!error) return;
    const bar = actionBarRef.current;
    if (!bar) return;
    const pinTop = () => {
      bar.scrollTop = 0;
    };
    const focusError = () => {
      saveErrorRef.current?.focus({ preventScroll: true });
    };
    pinTop();
    focusError();
    const frame = requestAnimationFrame(() => {
      pinTop();
      focusError();
    });
    return () => cancelAnimationFrame(frame);
  }, [error]);

  return (
    <AppLayout>
      {/* Column at least a screen tall, so the sticky action bar rests on the nav even when the content is short;
          -mb-4 cancels the scroll area's bottom padding, which would leave a strip under the bar.
          md:-mx-8 cancels the shell's 32px inset so the header and action bar stay full-bleed. */}
      <div className={`receipt-pane -mb-4 flex min-h-[calc(100dvh-var(--ff-nav-h))] flex-col md:-mx-8 lg:min-h-[100dvh]${desktopColumns ? ' lg:grid lg:grid-cols-[352px_minmax(24.75rem,36rem)_1fr] xl:grid-cols-[510px_minmax(24.75rem,36rem)_1fr] lg:grid-rows-[auto_1fr_auto] lg:gap-x-6' : ''}`}>
      {/* Header */}
      <header className="sticky top-0 z-40 bg-white border-b border-gray-200 safe-area-inset-top lg:col-span-full lg:row-start-1">
        <div className="flex items-center justify-between h-14 px-4 md:px-8">
          <Link href="/receipts" aria-label="Voltar aos recibos" className="p-3 -ml-3 touch-manipulation">
            <ArrowLeft className="w-5 h-5 text-gray-600" />
          </Link>
          <h1 className="text-lg font-semibold text-gray-900">Recibo</h1>
          <button
            onClick={handleDeleteClick}
            disabled={isDeleting}
            aria-label="Remover recibo"
            className="p-3 -mr-3 text-danger-500 touch-manipulation disabled:opacity-50"
          >
            {isDeleting ? <Loader2 className="w-5 h-5 animate-spin" /> : <Trash2 className="w-5 h-5" />}
          </button>
        </div>
      </header>

      {isLoading || (detailColumns && document) ? (
        <div
          data-testid="receipt-image-column"
          className={`px-4 pt-4 md:px-8 lg:sticky lg:top-14 lg:z-[45] lg:col-start-1 lg:row-start-2 lg:row-span-2 lg:self-start lg:pl-8 lg:pr-0 lg:pt-6${isLoading ? ' hidden lg:block' : ''}`}
        >
          <div className="card overflow-hidden lg:min-w-[320px]">
            <div
              data-testid="receipt-image-frame"
              className="aspect-[4/3] w-full bg-gray-100 lg:w-full lg:max-h-[calc(100dvh-8rem)] lg:min-h-[180px] lg:min-w-[320px] lg:[aspect-ratio:var(--receipt-image-aspect,3/4)]"
              style={{ '--receipt-image-aspect': imageAspect ? String(imageAspect) : '3 / 4' } as CSSProperties}
            >
              {document ? (
                <ImageViewer
                  src={document.file_url}
                  alt={document.vendor_name ? `Recibo de ${document.vendor_name}` : 'Recibo'}
                  mimeType={document.mime_type}
                  filename={document.original_filename}
                  onIntrinsicSize={reportImageSize}
                  className="h-full w-full"
                />
              ) : (
                <div className="h-full w-full animate-pulse bg-gray-200" />
              )}
            </div>
          </div>
        </div>
      ) : null}

      {/* Content */}
      <div data-testid={desktopColumns ? 'receipt-form-column' : undefined} className={`w-full flex-1 p-4 space-y-4 md:px-8${desktopColumns ? ' lg:col-start-2 lg:row-start-2 lg:px-0 lg:pt-6' : ''}`}>
        {isLoading ? (
          <div className="space-y-4">
            <div className="card aspect-[4/3] animate-pulse bg-gray-200 lg:hidden" />
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
            <button onClick={() => setReloadKey((key) => key + 1)} className="btn-secondary btn-md">
              Tentar de novo
            </button>
          </div>
        ) : document ? (
          <>
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
                    warning: <AlertTriangle className="w-4 h-4 text-[var(--ff-warning)] flex-shrink-0 mt-0.5" />,
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
                    className="-my-2 -mr-3 min-h-11 px-3 text-sm text-[var(--ff-text-muted)] touch-manipulation"
                  >
                    Cancelar
                  </button>
                </div>

                <div>
                  <label htmlFor="edit-document-type" className="block text-sm font-medium text-gray-700 mb-1">
                    Tipo de documento
                  </label>
                  <select
                    id="edit-document-type"
                    value={editData.document_type}
                    onChange={(e) => setEditData(d => ({ ...d, document_type: e.target.value }))}
                    className="input"
                  >
                    <option value="unclassified">Por classificar</option>
                    {DOCUMENT_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                  {document.suggested_type && document.document_type === 'unclassified' ? (
                    <p className="mt-1 text-sm text-[var(--ff-text-muted)]">
                      Sugestão: {documentTypeLabel(document.suggested_type)}
                    </p>
                  ) : null}
                  {document.at_document_type ? (
                    <p className="mt-1 text-sm text-[var(--ff-text-muted)]">Tipo AT: {document.at_document_type}</p>
                  ) : null}
                </div>

                <div>
                  <label htmlFor="edit-invoice-number" className="block text-sm font-medium text-gray-700 mb-1">
                    N.º da fatura
                  </label>
                  <input
                    id="edit-invoice-number"
                    type="text"
                    value={editData.invoice_number}
                    onChange={(e) => setEditData(d => ({ ...d, invoice_number: e.target.value }))}
                    className="input"
                  />
                  {document.suggested_invoice_number && document.document_type === 'unclassified' ? (
                    <p className="mt-1 text-sm text-[var(--ff-text-muted)]">
                      Sugestão de n.º {document.suggested_invoice_number}
                    </p>
                  ) : null}
                </div>

                <div>
                  <label htmlFor="edit-vendor-name" className="block text-sm font-medium text-gray-700 mb-1">Fornecedor</label>
                  <input
                    id="edit-vendor-name"
                    type="text"
                    value={editData.vendor_name}
                    onChange={(e) => setEditData(d => ({ ...d, vendor_name: e.target.value }))}
                    placeholder="Quem emitiu o recibo?"
                    className="input"
                  />
                </div>

                <PtDateInput
                  id="edit-document-date"
                  label="Data do documento"
                  value={editData.document_date}
                  onChange={(iso) => setEditData(d => ({ ...d, document_date: iso }))}
                  onValidityChange={(valid) => { editDateValidRef.current = valid; }}
                  max={new Date().toISOString().split('T')[0]}
                  labelClassName="block text-sm font-medium text-gray-700 mb-1"
                  inputClassName="input"
                />

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="edit-gross-amount" className="block text-sm font-medium text-gray-700 mb-1">Total (€)</label>
                    <input
                      id="edit-gross-amount"
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
                    <label htmlFor="edit-vat-amount" className="block text-sm font-medium text-gray-700 mb-1">IVA (€)</label>
                    <input
                      id="edit-vat-amount"
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
                {document.status === 'processing' && (
                  <div className="flex items-center gap-2 p-3 bg-blue-50 rounded-xl" role="status">
                    <Loader2 className="w-5 h-5 text-blue-600 animate-spin flex-shrink-0" aria-hidden="true" />
                    <p className="text-sm text-blue-800">A ler o recibo… os dados aparecem em segundos.</p>
                  </div>
                )}

                {/* Needs review alert */}
                {document.fictional ? (
                  <p className="text-sm text-amber-800">dados fictícios</p>
                ) : null}
                {document.status === 'needs_review' && !isComplete() && (
                  <div className="card p-3 bg-amber-50 border-amber-200 flex items-start gap-2">
                    <AlertCircle className="w-5 h-5 text-[var(--ff-warning)] flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-amber-800">
                      Alguns dados não foram lidos. Toque em Editar dados para os preencher.
                    </p>
                  </div>
                )}

                {/* Extracted data summary */}
                <div className="card divide-y divide-gray-100">
                  <div className="p-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0">
                      <Receipt className="w-5 h-5 text-[var(--ff-text-muted)]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-[var(--ff-text-muted)]">Tipo</p>
                      <p className="font-semibold text-gray-900">
                        {documentTypeLabel(document.document_type)}
                      </p>
                      {document.document_type === 'unclassified' && document.suggested_type ? (
                        <p className="text-sm text-[var(--ff-text-muted)]">Sugestão: {documentTypeLabel(document.suggested_type)}</p>
                      ) : null}
                      {document.at_document_type ? (
                        <p className="text-sm text-[var(--ff-text-muted)]">Tipo AT: {document.at_document_type}</p>
                      ) : null}
                      {(document.invoice_number || document.suggested_invoice_number) ? (
                        <p className="text-sm text-[var(--ff-text-muted)]">
                          {document.invoice_number
                            ? `N.º ${document.invoice_number}`
                            : `Sugestão de n.º ${document.suggested_invoice_number}`}
                        </p>
                      ) : null}
                    </div>
                  </div>

                  {/* Vendor */}
                  <div className="p-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0">
                      <Building2 className="w-5 h-5 text-[var(--ff-text-muted)]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-[var(--ff-text-muted)]">Fornecedor</p>
                      <p className="font-semibold text-gray-900 truncate">
                        {document.vendor_name || <span className="text-[var(--ff-text-muted)]">Não detetado</span>}
                      </p>
                    </div>
                  </div>

                  {/* Date */}
                  <div className="p-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0">
                      <Calendar className="w-5 h-5 text-[var(--ff-text-muted)]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-[var(--ff-text-muted)]">Data</p>
                      <p className="font-semibold text-gray-900">
                        {document.document_date ? formatDate(document.document_date) : <span className="text-[var(--ff-text-muted)]">Não detetado</span>}
                      </p>
                    </div>
                  </div>

                  {/* Total Amount */}
                  <div className="p-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                      <Euro className="w-5 h-5 text-primary-600" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm text-[var(--ff-text-muted)]">Total</p>
                      <p className="text-xl font-bold text-gray-900">
                        {document.gross_amount ? formatCurrency(document.gross_amount) : <span className="text-[var(--ff-text-muted)]">—</span>}
                      </p>
                    </div>
                    {/* VAT breakdown */}
                    {document.vat_amount && (
                      <div className="text-right">
                        <p className="text-xs text-[var(--ff-text-muted)]">IVA {getVatRateDisplay()}</p>
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
                  // aria-disabled rather than disabled: the sheet hands focus back here while the pick saves
                  return (
                    <button
                      onClick={() => !isSavingCategory && setShowCategoryPicker(true)}
                      aria-disabled={isSavingCategory}
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
                <label className="flex min-w-0 items-center justify-between gap-3 px-1 text-sm text-gray-600 max-[359px]:flex-col max-[359px]:items-stretch">
                  <span>IVA dedutível</span>
                  <select
                    value={document.deductible_pct_override ?? ''}
                    onChange={(e) => handleDeductibleChange(e.target.value)}
                    disabled={isSavingCategory}
                    className="input w-auto min-w-0 max-w-full py-1.5"
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
                    <span className="text-xs text-[var(--ff-text-muted)]">
                      Lido automaticamente
                    </span>
                    <span className={`text-xs font-medium ${
                      getConfidenceLevel() === 'high' ? 'text-[var(--ff-positive)]' :
                      getConfidenceLevel() === 'medium' ? 'text-[var(--ff-warning)]' : 'text-red-600'
                    }`}>
                      {parseFloat(document.ocr_confidence).toFixed(0)}% de confiança
                    </span>
                  </div>
                )}

                {/* Edit button */}
                <button
                  onClick={() => {
                    editDateValidRef.current = true;
                    setIsEditing(true);
                  }}
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
                  <Clock className="w-4 h-4 text-[var(--ff-text-muted)]" />
                  <span className="text-sm">
                    Histórico{auditTrail ? ` (${auditTrail.total})` : ''}
                  </span>
                </div>
                {showAuditTrail ? (
                  <ChevronUp className="w-4 h-4 text-[var(--ff-text-muted)]" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-[var(--ff-text-muted)]" />
                )}
              </button>

              {showAuditTrail && (
                <div className="mt-2 card p-4">
                  {isAuditLoading ? (
                    <div className="flex items-center justify-center py-4">
                      <Loader2 className="w-5 h-5 text-[var(--ff-text-muted)] animate-spin" />
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
                                <ActionIcon className="w-3.5 h-3.5 text-[var(--ff-text-muted)]" />
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
                                      <p key={field} className="text-xs text-[var(--ff-text-muted)]">
                                        <span className="font-medium">{field}:</span>{' '}
                                        <span className="text-[var(--ff-text-muted)]">{String(vals.old ?? '—')}</span>
                                        {' → '}
                                        <span className="text-gray-700">{String(vals.new ?? '—')}</span>
                                      </p>
                                    ))}
                                  </div>
                                )}

                                <p className="text-xs text-[var(--ff-text-muted)] mt-0.5">
                                  {relativeTime(entry.created_at)}
                                </p>
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ) : (
                    <p className="text-sm text-[var(--ff-text-muted)] text-center py-3">
                      Sem histórico disponível
                    </p>
                  )}
                </div>
              )}
            </div>

          </>
        ) : (
          <div className="card p-6 text-center">
            <AlertCircle className="w-12 h-12 text-danger-500 mx-auto mb-3" />
            <p className="text-gray-600 mb-4">{error || 'Não foi possível carregar o recibo.'}</p>
            <button onClick={() => setReloadKey((key) => key + 1)} className="btn-secondary btn-md">
              Tentar de novo
            </button>
          </div>
        )}
      </div>

      {/* Bottom action bar: sticks to the bottom of the scroll area, just above BottomNav; being in the flow, it never covers the content */}
      {document && !isLoading && (
        <div
          ref={actionBarRef}
          data-testid="receipt-action-bar"
          className="sticky bottom-0 z-40 max-h-[calc(100dvh-var(--ff-nav-h)-10rem)] overflow-y-auto border-t border-gray-200 bg-white p-4 md:px-8 lg:col-start-2 lg:row-start-3 lg:max-h-none lg:overflow-visible lg:px-0"
        >
          <div className="w-full">
            {/* In the action bar, so a 409 or 503 is not hidden under it on a small screen */}
            {error && (
              <div
                ref={saveErrorRef}
                role="alert"
                tabIndex={-1}
                className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-2 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-[#1b4d3e]"
              >
                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
                <span className="text-sm text-red-800">{error}</span>
              </div>
            )}
            <RateLimitNotice message={saveWait.message} className="mb-3" />
            {/* Keep the amounts in view next to the action that confirms them */}
            {!isEditing && (
              <dl className="flex justify-between text-sm mb-3" aria-label="Valores do recibo">
                <div className="flex gap-1.5">
                  <dt className="text-[var(--ff-text-muted)]">Total</dt>
                  <dd className="font-semibold text-gray-900">{formatCurrency(document.gross_amount)}</dd>
                </div>
                <div className="flex gap-1.5">
                  <dt className="text-[var(--ff-text-muted)]">IVA</dt>
                  <dd className="font-semibold text-gray-900">{formatCurrency(document.vat_amount)}</dd>
                </div>
              </dl>
            )}
            {isEditing ? (
              <>
              {editSeriesMismatch ? (
                <div className="mb-3 space-y-2">
                  <p className="text-sm text-red-700">{SERIES_MISMATCH_DETAIL}</p>
                  {editCanOverride ? (
                    <>
                      <p className="text-sm text-amber-800">{SERIES_OVERRIDE_WARNING}</p>
                      <label className="flex min-h-11 items-start gap-2 text-sm text-gray-800 lg:min-h-0">
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={acceptSeriesMismatch}
                          onChange={(event) => setAcceptSeriesMismatch(event.target.checked)}
                        />
                        <span>{PRINTED_PAIR_LABEL}</span>
                      </label>
                    </>
                  ) : null}
                </div>
              ) : null}
              <button
                {...softDisabled(isSaving || saveWait.seconds !== null)}
                onClick={handleSaveEdit}
                disabled={editSeriesMismatch && (!editCanOverride || !acceptSeriesMismatch)}
                className="btn-primary btn-lg w-full flex items-center justify-center gap-2"
              >
                {isSaving ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    A guardar...
                  </>
                ) : saveWait.seconds !== null ? (
                  <>
                    <Clock className="w-5 h-5" aria-hidden="true" />
                    <RateLimitButtonText seconds={saveWait.seconds} />
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-5 h-5" />
                    {editIsConcrete ? 'Guardar e confirmar' : 'Guardar'}
                  </>
                )}
              </button>
              </>
            ) : (
              <>
              {!isConcreteDocumentType(document.document_type) ? (
                <div className="mb-3 space-y-2">
                  <label htmlFor="confirm-document-type" className="block text-sm font-medium text-gray-700">
                    Tipo de documento
                  </label>
                  <select
                    id="confirm-document-type"
                    value={confirmType}
                    onChange={(e) => setConfirmType(e.target.value)}
                    className="input"
                  >
                    <option value="unclassified">Por classificar</option>
                    {DOCUMENT_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                  {document.suggested_type ? (
                    <p className="text-sm text-[var(--ff-text-muted)]">
                      Sugestão: {documentTypeLabel(document.suggested_type)}
                    </p>
                  ) : null}
                </div>
              ) : null}
              {confirmSeriesMismatch ? (
                <div className="mb-3 space-y-2">
                  <p className="text-sm text-red-700">{SERIES_MISMATCH_DETAIL}</p>
                  {confirmCanOverride ? (
                    <>
                      <p className="text-sm text-amber-800">{SERIES_OVERRIDE_WARNING}</p>
                      <label className="flex min-h-11 items-start gap-2 text-sm text-gray-800 lg:min-h-0">
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={acceptSeriesMismatch}
                          onChange={(event) => setAcceptSeriesMismatch(event.target.checked)}
                        />
                        <span>{PRINTED_PAIR_LABEL}</span>
                      </label>
                    </>
                  ) : null}
                </div>
              ) : null}
              <button
                {...softDisabled(isSaving || saveWait.seconds !== null)}
                onClick={handleConfirm}
                disabled={!isConcreteDocumentType(confirmChosen) || (confirmSeriesMismatch && (!confirmCanOverride || !acceptSeriesMismatch))}
                className="btn-primary btn-lg w-full flex items-center justify-center gap-2"
              >
                {isSaving ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    A guardar...
                  </>
                ) : saveWait.seconds !== null ? (
                  <>
                    <Clock className="w-5 h-5" aria-hidden="true" />
                    <RateLimitButtonText seconds={saveWait.seconds} />
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-5 h-5" />
                    Está correto
                  </>
                )}
              </button>
              </>
            )}
          </div>
        </div>
      )}
      </div>

      {/* Category Picker Bottom Sheet */}
      {showCategoryPicker && (
        <ModalLayer layer="sheet" onClose={() => setShowCategoryPicker(false)} className="flex items-end justify-center bg-black/50">
          <div 
            role="dialog"
            aria-modal="true"
            aria-labelledby="category-picker-title"
            className="bg-white rounded-t-2xl shadow-xl w-full max-w-lg animate-in slide-in-from-bottom duration-200 max-h-[70vh] flex flex-col"
          >
            <div className="flex items-center justify-between p-4 border-b border-gray-100">
              <h2 id="category-picker-title" className="text-lg font-semibold text-gray-900">Categoria</h2>
              <button onClick={() => setShowCategoryPicker(false)} aria-label="Fechar" className="p-3 -m-2 text-[var(--ff-text-muted)] touch-manipulation">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="overflow-y-auto p-2 pb-[calc(0.5rem+env(safe-area-inset-bottom,0px))]">
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
        </ModalLayer>
      )}

      {/* Delete Modal */}
      {showDeleteModal && (
        <ModalLayer
          layer="sheet"
          onClose={handleDeleteCancel}
          className="flex items-end sm:items-center justify-center p-4 pb-[calc(1rem+env(safe-area-inset-bottom,0px))] bg-black/50"
        >
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-modal-title"
            className="bg-white rounded-t-2xl sm:rounded-2xl shadow-xl w-full max-w-sm p-6 animate-in slide-in-from-bottom sm:zoom-in duration-200"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 id="delete-modal-title" className="text-lg font-semibold text-gray-900">Remover recibo</h2>
              <button onClick={handleDeleteCancel} aria-label="Fechar" className="p-3 -m-2 text-[var(--ff-text-muted)] touch-manipulation">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            {/* Conversion Lead owns this copy (COPY-TOKENS-v1). No retention or legal claim. */}
            <p className="text-gray-600 mb-6">
              O recibo deixa de aparecer na lista, no resumo e na exportação.
            </p>

            {deleteError && (
              <p role="alert" className="-mt-2 mb-4 text-sm text-red-600">
                {deleteError}
              </p>
            )}
            
            <div className="flex gap-3">
              <button
                data-autofocus
                onClick={handleDeleteCancel}
                disabled={isDeleting}
                className="flex-1 btn-secondary btn-md min-h-11"
              >
                Cancelar
              </button>
              <button
                onClick={handleDeleteConfirm}
                disabled={isDeleting}
                className="flex-1 btn-danger min-h-11 px-4 py-2.5 gap-2"
              >
                {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                Remover
              </button>
            </div>
          </div>
        </ModalLayer>
      )}
    </AppLayout>
  );
}
