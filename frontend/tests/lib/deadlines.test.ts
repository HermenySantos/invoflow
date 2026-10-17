import { describe, expect, it } from 'vitest';
import { formatPaymentDeadline, paymentDeadline } from '@/lib/deadlines';

describe('paymentDeadline', () => {
  it('puts Q1 on 20 May and moves Q2 2026 off Sunday 20 September', () => {
    const q1 = paymentDeadline('quarter', 2026, 1);
    const q2 = paymentDeadline('quarter', 2026, 2);
    expect(q1.getFullYear()).toBe(2026);
    expect(q1.getMonth()).toBe(4);
    expect(q1.getDate()).toBe(20);
    expect(q2.getFullYear()).toBe(2026);
    expect(q2.getMonth()).toBe(8);
    expect(q2.getDate()).toBe(21);
    expect(formatPaymentDeadline(q1, 'pt')).toBe('Prazo de entrega: 20 de maio de 2026');
    expect(formatPaymentDeadline(q2, 'en')).toBe('Filing deadline: 21 September 2026');
  });

  it('moves Q4 2026 off Saturday 20 February to Monday 22 February 2027', () => {
    const q4 = paymentDeadline('quarter', 2026, 4);
    expect(q4.getFullYear()).toBe(2027);
    expect(q4.getMonth()).toBe(1);
    expect(q4.getDate()).toBe(22);
  });

  it('uses the 20th of the second following month, then the next working day', () => {
    const march = paymentDeadline('month', 2026, 3);
    expect(march.getFullYear()).toBe(2026);
    expect(march.getMonth()).toBe(4);
    expect(march.getDate()).toBe(20);
    const october = paymentDeadline('month', 2026, 10);
    expect(october.getFullYear()).toBe(2026);
    expect(october.getMonth()).toBe(11);
    expect(october.getDate()).toBe(21);
  });

  it('files the June declaration on 20 September, then the next working day', () => {
    const june = paymentDeadline('month', 2026, 6);
    expect(june.getFullYear()).toBe(2026);
    expect(june.getMonth()).toBe(8);
    expect(june.getDate()).toBe(21);
  });

  it('moves a deadline that lands on Good Friday past the Easter weekend', () => {
    const february = paymentDeadline('month', 2057, 2);
    expect(february.getFullYear()).toBe(2057);
    expect(february.getMonth()).toBe(3);
    expect(february.getDate()).toBe(23);
  });
});