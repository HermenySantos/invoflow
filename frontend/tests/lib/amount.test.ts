import { describe, expect, it } from 'vitest';
import { parseAmountInput } from '@/lib/amount';

describe('parseAmountInput', () => {
  it.each([
    ['1.234,56', '1234.56'],
    ['1234,5', '1234.50'],
    ['1,234.56', '1234.56'],
    ['1.234', '1234.00'],
    ['€ 12,40', '12.40'],
    ['0', '0.00'],
  ])('reads %s as %s', (input, expected) => {
    expect(parseAmountInput(input)).toBe(expected);
  });

  it.each(['', 'abc', '-5', '12,4,a'])('rejects %s', (input) => {
    expect(parseAmountInput(input)).toBeNull();
  });
});
