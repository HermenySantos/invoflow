import { describe, expect, it } from 'vitest';
import { formatPaymentDeadline, paymentDeadline } from '@/lib/deadlines';

describe('paymentDeadline', () => {
  it('puts Q1 on 20 May and Q2 on 20 September', () => {
    const q1 = paymentDeadline('quarter', 2026, 1);
    const q2 = paymentDeadline('quarter', 2026, 2);
    expect(q1.getFullYear()).toBe(2026);
    expect(q1.getMonth()).toBe(4);
    expect(q1.getDate()).toBe(20);
    expect(q2.getFullYear()).toBe(2026);
    expect(q2.getMonth()).toBe(8);
    expect(q2.getDate()).toBe(20);
    expect(formatPaymentDeadline(q1, 'pt')).toBe('Prazo 20 de maio de 2026');
    expect(formatPaymentDeadline(q2, 'en')).toBe('Due 20 September 2026');
  });

  it('keeps a monthly deadline on the 20th of the next month', () => {
    const march = paymentDeadline('month', 2026, 3);
    expect(march.getMonth()).toBe(3);
    expect(march.getDate()).toBe(20);
  });
});