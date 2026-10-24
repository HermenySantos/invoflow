import { describe, expect, it } from 'vitest';
import { documentTypeLabel, initialReviewEdit, saveEditPayload } from '@/lib/reviewEdit';

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
  it('prefills a suggestion and does not treat it as confirmed', () => {
    expect(initialReviewEdit({
      document_type: 'unclassified',
      suggested_type: 'FR',
      suggested_invoice_number: 'FR A/5',
      vendor_name: 'Ana',
      document_date: '2026-03-31',
      gross_amount: '12.30',
      vat_amount: '2.30',
    })).toMatchObject({
      document_type: 'FR',
      invoice_number: 'FR A/5',
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
