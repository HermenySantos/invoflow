export interface ReviewEditFields {
  vendor_name: string;
  document_date: string;
  gross_amount: string;
  vat_amount: string;
  net_amount?: string;
  document_type?: string;
}

/** PT-PT labels for the two types a reviewer is asked to confirm. */
export function documentTypeLabel(code: string | null | undefined): string {
  if (code === 'FT') return 'Fatura';
  if (code === 'NC') return 'Nota de crédito';
  if (code) return code;
  return 'Por classificar';
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
  return {
    vendor_name: editData.vendor_name || null,
    document_date: editData.document_date || null,
    gross_amount: editData.gross_amount || null,
    vat_amount: editData.vat_amount || null,
    ...(net !== null ? { net_amount: net } : {}),
    ...(editData.document_type ? { document_type: editData.document_type } : {}),
    status: 'ready' as const,
  };
}
