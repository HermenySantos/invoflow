export interface ReviewEditFields {
  vendor_name: string;
  document_date: string;
  gross_amount: string;
  vat_amount: string;
  net_amount?: string;
  document_type?: string;
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
    status: (draft ? 'needs_review' : 'ready') as 'ready' | 'needs_review',
  };
}
