import { describe, expect, it } from 'vitest';
import { saveEditPayload } from '@/lib/reviewEdit';

describe('saveEditPayload', () => {
  it('keeps a negative credit-note total', () => {
    expect(
      saveEditPayload({
        vendor_name: 'Padaria Central',
        document_date: '2026-04-15',
        gross_amount: '-10.00',
        vat_amount: '-1.87',
      })
    ).toEqual({
      vendor_name: 'Padaria Central',
      document_date: '2026-04-15',
      gross_amount: '-10.00',
      vat_amount: '-1.87',
      status: 'ready',
    });
  });
});
