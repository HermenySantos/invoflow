import { describe, expect, it } from 'vitest';
import {
  SERIES_MISMATCH_DETAIL,
  documentTypeLabel,
  initialReviewEdit,
  invoiceSeriesPrefix,
  saveEditPayload,
  seriesAgrees,
  seriesBlocks,
  seriesOverrideAllowed,
} from '@/lib/reviewEdit';

describe('saveEditPayload', () => {
  it('sends the edited non-negative total and the net that matches it', () => {
    expect(
      saveEditPayload({
        vendor_name: 'Ana Exemplo',
        document_date: '2026-04-15',
        gross_amount: '10.00',
        vat_amount: '1.87',
      })
    ).toEqual({
      vendor_name: 'Ana Exemplo',
      document_date: '2026-04-15',
      gross_amount: '10.00',
      vat_amount: '1.87',
      net_amount: '8.13',
      status: 'ready',
    });
  });

  it('recomputes net when the gross total is corrected and IVA stays', () => {
    expect(
      saveEditPayload({
        vendor_name: 'Ana Exemplo',
        document_date: '2026-03-31',
        gross_amount: '15.00',
        vat_amount: '2.30',
        net_amount: '10.00',
        document_type: 'FT',
      })
    ).toEqual({
      vendor_name: 'Ana Exemplo',
      document_date: '2026-03-31',
      gross_amount: '15.00',
      vat_amount: '2.30',
      net_amount: '12.70',
      document_type: 'FT',
      status: 'ready',
    });
  });

  it('does not invent a net when IVA or the total is empty', () => {
    const payload = saveEditPayload({
      vendor_name: '',
      document_date: '',
      gross_amount: '15.00',
      vat_amount: '',
    });
    expect(payload).not.toHaveProperty('net_amount');
    expect(payload.gross_amount).toBe('15.00');
    expect(payload.vat_amount).toBeNull();
  });
});

describe('documentTypeLabel', () => {
  it('uses the Portuguese labels', () => {
    expect(documentTypeLabel('FT')).toBe('Fatura');
    expect(documentTypeLabel('FS')).toBe('Fatura simplificada');
    expect(documentTypeLabel('FR')).toBe('Fatura-recibo');
    expect(documentTypeLabel('NC')).toBe('Nota de crédito');
    expect(documentTypeLabel('ND')).toBe('Nota de débito');
    expect(documentTypeLabel(null)).toBe('Por classificar');
    expect(documentTypeLabel('unclassified')).toBe('Por classificar');
  });
});

describe('initialReviewEdit', () => {
  it('does not preselect a suggestion on an unclassified row', () => {
    expect(initialReviewEdit({
      document_type: 'unclassified',
      suggested_type: 'FR',
      suggested_invoice_number: 'FR A/5',
      vendor_name: 'Ana',
      document_date: '2026-03-31',
      gross_amount: '12.30',
      vat_amount: '2.30',
    })).toMatchObject({
      document_type: 'unclassified',
      invoice_number: '',
    });
  });

  it('keeps a confirmed type and number ahead of a suggestion', () => {
    expect(initialReviewEdit({
      document_type: 'NC',
      suggested_type: 'FT',
      invoice_number: 'NC A/1',
      suggested_invoice_number: 'FT A/12',
    })).toMatchObject({
      document_type: 'NC',
      invoice_number: 'NC A/1',
    });
  });
});

describe('invoice series prefix', () => {
  it('recognises a series at the start and ignores everything else', () => {
    expect(invoiceSeriesPrefix('FT A/12')).toBe('FT');
    expect(invoiceSeriesPrefix('NC-A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('NCA/5')).toBe('NC');
    expect(invoiceSeriesPrefix('N/C')).toBe('NC');
    expect(invoiceSeriesPrefix('N/C n.º 7')).toBe('NC');
    expect(invoiceSeriesPrefix('N.C 1')).toBe('NC');
    expect(invoiceSeriesPrefix('N-C 1')).toBe('NC');
    expect(invoiceSeriesPrefix('  fs 1')).toBe('FS');
    expect(invoiceSeriesPrefix('INV-100')).toBeNull();
    expect(invoiceSeriesPrefix('CN-2026-7')).toBeNull();
    expect(invoiceSeriesPrefix('Q2/7')).toBeNull();
    expect(invoiceSeriesPrefix('FRANGO')).toBeNull();
    expect(invoiceSeriesPrefix('frete 12')).toBeNull();
    expect(invoiceSeriesPrefix('fr001')).toBeNull();
    expect(invoiceSeriesPrefix('FS2026/12')).toBeNull();
    expect(invoiceSeriesPrefix('FRA2026/12')).toBeNull();
    expect(invoiceSeriesPrefix('Fr. 12')).toBeNull();
    expect(invoiceSeriesPrefix('FRA 2026/12')).toBeNull();
    expect(invoiceSeriesPrefix('FT2026/1')).toBeNull();
    expect(invoiceSeriesPrefix('NC2026/5')).toBe('NC');
    expect(invoiceSeriesPrefix('ND2026/3')).toBe('ND');
    expect(invoiceSeriesPrefix('Fr.12')).toBeNull();
    expect(invoiceSeriesPrefix('Fs.12')).toBeNull();
    expect(invoiceSeriesPrefix('Nc.12')).toBeNull();
    expect(invoiceSeriesPrefix('NC1')).toBeNull();
    expect(invoiceSeriesPrefix('nd.2026')).toBeNull();
    expect(invoiceSeriesPrefix('fr.a')).toBe('FR');
    expect(invoiceSeriesPrefix('N\u200bC A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('\uFEFFNC A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('N\u00adC A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('\u0143\u0106 A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('N\u2010C A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('N\u2013C')).toBe('NC');
    expect(invoiceSeriesPrefix('N\u2044C A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('\u0274\u1d04 A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('\ua4e0C A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('\ua4e0\ua4da A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('nc a/5')).toBe('NC');
    expect(invoiceSeriesPrefix('N C A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('NC.A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('N.C. A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('N/C A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('  NC A/5  ')).toBe('NC');
    expect(invoiceSeriesPrefix('NC\tA/5')).toBe('NC');
    expect(invoiceSeriesPrefix('NC\u00A0A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('N\u0421 A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('\u041DC A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('\uFF2E\uFF23 A/5')).toBe('NC');
    expect(invoiceSeriesPrefix('')).toBeNull();
    expect(invoiceSeriesPrefix(null)).toBeNull();
  });

  it('rejects only a concrete type that disagrees with the prefix', () => {
    expect(seriesAgrees('NC', 'FT A/12')).toBe(false);
    expect(seriesAgrees('FT', 'NCA/5')).toBe(false);
    expect(seriesAgrees('NC', 'NC Q2/7')).toBe(true);
    expect(seriesAgrees('NC', 'INV-100')).toBe(true);
    expect(seriesAgrees('FT', 'FRANGO')).toBe(true);
    expect(seriesAgrees('unclassified', 'FT A/12')).toBe(true);
    expect(seriesAgrees('NC', '')).toBe(true);
    expect(seriesAgrees('NC', null)).toBe(true);
    expect(seriesAgrees('FT', 'frete 12')).toBe(true);
    expect(seriesAgrees('FT', 'FRA2026/12')).toBe(true);
    expect(seriesAgrees('FT', 'Fr. 12')).toBe(true);
    expect(seriesAgrees('FT', 'Fr.12')).toBe(true);
    expect(seriesAgrees('FT', 'Fs.12')).toBe(true);
    expect(seriesAgrees('FT', 'Nc.12')).toBe(true);
    expect(seriesAgrees('FT', 'NC1')).toBe(true);
    expect(seriesAgrees('FT', 'nd.2026')).toBe(true);
    expect(seriesAgrees('FT', 'fr.a')).toBe(false);
    expect(seriesAgrees('FT', 'FRA 2026/12')).toBe(true);
    expect(seriesAgrees('FT', 'NC2026/5')).toBe(false);
    expect(seriesAgrees('FT', 'N\u200bC A/5')).toBe(false);
    expect(seriesAgrees('FT', 'N\u0421 A/5')).toBe(false);
    expect(seriesAgrees('FT', '\u041DC A/5')).toBe(false);
    expect(seriesAgrees('FT', '\uFF2E\uFF23 A/5')).toBe(false);
    expect(SERIES_MISMATCH_DETAIL).toBe('O n.º do documento não corresponde ao tipo indicado.');
  });

  it('lets an unchanged AT pair through and still blocks a different pair', () => {
    expect(seriesBlocks('FR', 'FT 2026/12', 'FR', 'FT 2026/12')).toBe(false);
    expect(seriesBlocks('FR', 'FTR A/12', 'FR', 'FTR A/12')).toBe(false);
    expect(seriesBlocks('FS', 'FT A/12', 'FS', 'FT A/12')).toBe(false);
    expect(seriesBlocks('ND', 'NC A/3', 'ND', 'NC A/3')).toBe(false);
    expect(seriesBlocks('NC', 'FT A/12')).toBe(true);
    expect(seriesBlocks('NC', 'FT 2026/12', 'FR', 'FT 2026/12')).toBe(true);
    expect(seriesBlocks('FT', 'frete 12')).toBe(false);
    expect(seriesBlocks('unclassified', 'FT A/12', 'FR', 'FT 2026/12')).toBe(false);
  });

  it('offers the printed-pair flag only inside the invoice family and never on an AT row', () => {
    expect(seriesOverrideAllowed('FR', 'FT 2026/12', null, null)).toBe(true);
    expect(seriesOverrideAllowed('FS', 'FR 1/5', null, null)).toBe(true);
    expect(seriesOverrideAllowed('FT', 'FT A/12', null, null)).toBe(false);
    expect(seriesOverrideAllowed('NC', 'FT A/12', null, null)).toBe(false);
    expect(seriesOverrideAllowed('FT', 'NC A/5', null, null)).toBe(false);
    expect(seriesOverrideAllowed('FT', 'NC2026/5', null, null)).toBe(false);
    expect(seriesOverrideAllowed('ND', 'FT 2026/12', null, null)).toBe(false);
    expect(seriesOverrideAllowed('FR', 'FT 2026/12', 'FR', 'FT 2026/12')).toBe(false);
    expect(seriesOverrideAllowed('NC', 'FT 2026/12', 'FR', 'FT 2026/12')).toBe(false);
    expect(seriesOverrideAllowed('FS', 'FT 2026/12', 'FR', 'FT 2026/12')).toBe(false);
    expect(seriesOverrideAllowed('FT', 'Fr.12', null, null)).toBe(false);
    expect(seriesOverrideAllowed('FT', 'NC1', null, null)).toBe(false);
  });
});

describe('saveEditPayload drafts', () => {
  it('keeps Por classificar as a draft', () => {
    const payload = saveEditPayload({
      vendor_name: 'Ana Exemplo',
      document_date: '2026-03-31',
      gross_amount: '12.30',
      vat_amount: '2.30',
      document_type: 'unclassified',
    });
    expect(payload.document_type).toBe('unclassified');
    expect(payload.status).toBe('needs_review');
    expect(payload.net_amount).toBe('10.00');
  });
});
