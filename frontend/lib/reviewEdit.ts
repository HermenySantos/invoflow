export interface ReviewEditFields {
  vendor_name: string;
  document_date: string;
  gross_amount: string;
  vat_amount: string;
  net_amount?: string;
  document_type?: string;
  invoice_number?: string;
}

const CONCRETE_TYPES = new Set(['FT', 'FS', 'FR', 'NC', 'ND']);

/** A stored or explicitly picked AT type. A suggestion is not one. */
export function isConcreteDocumentType(code: string | null | undefined): boolean {
  return !!code && CONCRETE_TYPES.has(code);
}

/** Prefill the review form. A suggestion never fills the type or the number. */
export function initialReviewEdit(document: {
  vendor_name?: string | null;
  document_date?: string | null;
  gross_amount?: string | null;
  vat_amount?: string | null;
  document_type?: string | null;
  suggested_type?: string | null;
  invoice_number?: string | null;
  suggested_invoice_number?: string | null;
}) {
  const confirmed = isConcreteDocumentType(document.document_type);
  return {
    vendor_name: document.vendor_name || '',
    document_date: document.document_date || '',
    gross_amount: document.gross_amount || '',
    vat_amount: document.vat_amount || '',
    document_type: confirmed ? document.document_type! : 'unclassified',
    invoice_number: document.invoice_number || '',
  };
}

export const DOCUMENT_TYPE_OPTIONS = [
  { value: 'FT', label: 'Fatura' },
  { value: 'FS', label: 'Fatura simplificada' },
  { value: 'FR', label: 'Fatura-recibo' },
  { value: 'NC', label: 'Nota de crédito' },
  { value: 'ND', label: 'Nota de débito' },
] as const;

/** PT-PT label. An empty type and 'unclassified' are both 'Por classificar'. */
export function documentTypeLabel(code: string | null | undefined): string {
  if (!code || code === 'unclassified') return 'Por classificar';
  return DOCUMENT_TYPE_OPTIONS.find((option) => option.value === code)?.label ?? code;
}

/**
 * Net sent with a gross correction. Empty IVA or total does not invent a net.
 * Cents avoid binary float (15.00 − 2.30 = 12.70).
 */
function netFromGrossAndVat(gross: string, vat: string): string | null {
  if (gross === '' || vat === '') return null;
  const grossCents = Math.round(Number(gross) * 100);
  const vatCents = Math.round(Number(vat) * 100);
  if (!Number.isFinite(grossCents) || !Number.isFinite(vatCents)) return null;
  const netCents = grossCents - vatCents;
  if (netCents < 0) return null;
  return (netCents / 100).toFixed(2);
}

/** Payload for the receipt review save. Amounts stay non-negative; NC is the sign. */
export function saveEditPayload(editData: ReviewEditFields) {
  const net = netFromGrossAndVat(editData.gross_amount, editData.vat_amount);
  const chosen = editData.document_type;
  const draft = chosen === 'unclassified';
  return {
    vendor_name: editData.vendor_name || null,
    document_date: editData.document_date || null,
    gross_amount: editData.gross_amount || null,
    vat_amount: editData.vat_amount || null,
    ...(net !== null ? { net_amount: net } : {}),
    ...(chosen ? { document_type: chosen } : {}),
    ...('invoice_number' in editData ? { invoice_number: editData.invoice_number || null } : {}),
    status: (draft ? 'needs_review' : 'ready') as 'ready' | 'needs_review',
  };
}
