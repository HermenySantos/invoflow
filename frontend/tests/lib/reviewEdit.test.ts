import { describe, expect, it } from 'vitest';
import {
  SERIES_MISMATCH_DETAIL,
  documentTypeLabel,
  initialReviewEdit,
  invoiceSeriesPrefix,
  saveEditPayload,
  seriesAgrees,
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
    expect(SERIES_MISMATCH_DETAIL).toBe('O n.º do documento não corresponde ao tipo indicado.');
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
