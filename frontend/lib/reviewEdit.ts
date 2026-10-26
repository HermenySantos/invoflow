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

/** Shown when a series prefix and the chosen type disagree. Same string as the API 422. */
export const SERIES_MISMATCH_DETAIL = 'O n.º do documento não corresponde ao tipo indicado.';

/** Shown when the user may keep a printed pair the QR could not confirm. */
export const SERIES_OVERRIDE_WARNING =
  'O n.º não corresponde ao tipo. Confirme só se for o par impresso no documento.';

export const PRINTED_PAIR_LABEL = 'Confirmo que este é o par impresso no documento.';

// A dot counts only when a letter or digit follows ("NC.A/5"). "Fr. 12" does not.
const SERIES_TOKEN = /^(FT|FS|FR|NC|ND)(?=[\s/\-]|$|\.(?=[A-Za-z0-9]))/i;
// "NC2026/5". Purchase codes glued to digits are vendor numbering.
const SERIES_GLUED_DIGIT = /^(NC|ND)(?=\d)/i;
// "NCA/5": one extra letter, then / . or -. Whitespace does not count ("FRA 2026/12").
const SERIES_GLUED_LETTER = /^(FT|FS|FR|NC|ND)[A-Za-z](?=[/.\-])/i;
// "N/C", "N.C", "N-C", "N C A/5", "N.C. A/5".
const SERIES_SPLIT = /^([A-Za-z])[\s./\-]+([A-Za-z])(?=[\s/.\-]|$)/;

// Cyrillic and Greek letters that stand in for the Latin series codes.
// U+041D (Н) folds to N so "НC" is the NC series.
const CONFUSABLES = new Map<number, string>([
  [0x0391, 'A'], [0x03b1, 'a'],
  [0x0392, 'B'], [0x03b2, 'b'],
  [0x0395, 'E'], [0x03b5, 'e'],
  [0x0396, 'Z'], [0x03b6, 'z'],
  [0x0397, 'H'], [0x03b7, 'h'],
  [0x0399, 'I'], [0x03b9, 'i'],
  [0x039a, 'K'], [0x03ba, 'k'],
  [0x039c, 'M'], [0x03bc, 'm'],
  [0x039d, 'N'], [0x03bd, 'n'],
  [0x039f, 'O'], [0x03bf, 'o'],
  [0x03a1, 'P'], [0x03c1, 'p'],
  [0x03a4, 'T'], [0x03c4, 't'],
  [0x03a5, 'Y'], [0x03c5, 'y'],
  [0x03a7, 'X'], [0x03c7, 'x'],
  [0x0410, 'A'], [0x0430, 'a'],
  [0x0412, 'B'], [0x0432, 'b'],
  [0x0415, 'E'], [0x0435, 'e'],
  [0x041a, 'K'], [0x043a, 'k'],
  [0x041c, 'M'], [0x043c, 'm'],
  [0x041d, 'N'], [0x043d, 'n'],
  [0x041e, 'O'], [0x043e, 'o'],
  [0x0420, 'P'], [0x0440, 'p'],
  [0x0421, 'C'], [0x0441, 'c'],
  [0x0422, 'T'], [0x0442, 't'],
  [0x0423, 'Y'], [0x0443, 'y'],
  [0x0425, 'X'], [0x0445, 'x'],
  [0x0406, 'I'], [0x0456, 'i'],
  [0x0407, 'I'], [0x0457, 'i'],
  [0x0408, 'J'], [0x0458, 'j'],
  [0x0274, 'N'],
  [0x1d04, 'C'],
  [0xa730, 'F'],
  [0x1d1b, 'T'],
  [0xa731, 'S'],
  [0x0280, 'R'],
  [0x1d05, 'D'],
  [0xa4e0, 'N'],
  [0xa4da, 'C'],
]);

const UNICODE_HYPHEN = /[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]/g;
const UNICODE_SLASH = /[\u2044\u2215\u29F8\uFF0F]/g;

/** NFKC, drop format characters, fold lookalikes, accents, hyphens and slashes. */
export function foldSeriesText(value: string | null | undefined): string {
  if (value == null || value === '') return '';
  const nfkc = value.normalize('NFKC').replace(/\p{Cf}/gu, '');
  let folded = '';
  for (const ch of nfkc) {
    const code = ch.codePointAt(0);
    folded += code === undefined ? ch : (CONFUSABLES.get(code) ?? ch);
  }
  return folded
    .normalize('NFD')
    .replace(/\p{Mn}/gu, '')
    .replace(UNICODE_HYPHEN, '-')
    .replace(UNICODE_SLASH, '/')
    .trim();
}

/** A stored or explicitly picked AT type. A suggestion is not one. */
export function isConcreteDocumentType(code: string | null | undefined): boolean {
  return !!code && CONCRETE_TYPES.has(code);
}

/**
 * FT, FS, FR, NC or ND as a token at the start of a document number.
 * 'NC-A/5', 'NCA/5', 'N/C', 'N C A/5' and 'NC2026/5' count.
 * 'frete 12', 'fr001', 'FS2026/12', 'Fr. 12' and 'FRA 2026/12' do not.
 */
export function invoiceSeriesPrefix(number: string | null | undefined): string | null {
  const text = foldSeriesText(number);
  if (!text) return null;
  const token = SERIES_TOKEN.exec(text);
  if (token) return token[1].toUpperCase();
  const gluedDigit = SERIES_GLUED_DIGIT.exec(text);
  if (gluedDigit) return gluedDigit[1].toUpperCase();
  const glued = SERIES_GLUED_LETTER.exec(text);
  if (glued) return glued[1].toUpperCase();
  const split = SERIES_SPLIT.exec(text);
  if (!split) return null;
  const code = (split[1] + split[2]).toUpperCase();
  if (!CONCRETE_TYPES.has(code)) return null;
  return code;
}

/** A concrete type agrees with its number, or the number has no series prefix. */
export function seriesAgrees(
  documentType: string | null | undefined,
  invoiceNumber: string | null | undefined,
): boolean {
  if (!isConcreteDocumentType(documentType)) return true;
  const prefix = invoiceSeriesPrefix(invoiceNumber);
  return prefix === null || prefix === documentType;
}

function sameSeriesText(left: string | null | undefined, right: string | null | undefined): boolean {
  return foldSeriesText(left).toUpperCase() === foldSeriesText(right).toUpperCase();
}

/** True when the chosen type and number are still the pair AT issued. */
export function isAtIssuedPair(
  atType: string | null | undefined,
  atNumber: string | null | undefined,
  documentType: string | null | undefined,
  invoiceNumber: string | null | undefined,
): boolean {
  if (!atType || atNumber == null || atNumber === '') return false;
  return sameSeriesText(documentType, atType) && sameSeriesText(invoiceNumber, atNumber);
}

/**
 * Block a save or a confirm when a concrete type disagrees with the number.
 * An unchanged AT pair is legal, so it is not a mismatch.
 */
export function seriesBlocks(
  documentType: string | null | undefined,
  invoiceNumber: string | null | undefined,
  atType?: string | null,
  atNumber?: string | null,
): boolean {
  if (isAtIssuedPair(atType, atNumber, documentType, invoiceNumber)) return false;
  return !seriesAgrees(documentType, invoiceNumber);
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
export function saveEditPayload(editData: ReviewEditFields, acceptSeriesMismatch = false) {
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
    ...(acceptSeriesMismatch ? { accept_series_mismatch: true } : {}),
  };
}
