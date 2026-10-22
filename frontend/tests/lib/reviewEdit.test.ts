import { describe, expect, it } from 'vitest';
import { documentTypeLabel, saveEditPayload } from '@/lib/reviewEdit';

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
    expect(documentTypeLabel('NC')).toBe('Nota de crédito');
    expect(documentTypeLabel(null)).toBe('Por classificar');
    expect(documentTypeLabel('FR')).toBe('FR');
  });
});
