export interface ReviewEditFields {
  vendor_name: string;
  document_date: string;
  gross_amount: string;
  vat_amount: string;
}

/** Payload for the receipt review save. Amounts stay non-negative; NC is the sign. */
export function saveEditPayload(editData: ReviewEditFields) {
  return {
    vendor_name: editData.vendor_name || null,
    document_date: editData.document_date || null,
    gross_amount: editData.gross_amount || null,
    vat_amount: editData.vat_amount || null,
    status: 'ready' as const,
  };
}
