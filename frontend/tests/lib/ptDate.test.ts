import { describe, expect, it } from 'vitest';
import { formatPtDate, maskPtDate, parsePtDate } from '@/lib/ptDate';

describe('parsePtDate', () => {
  it('reads dd/mm/aaaa as ISO yyyy-mm-dd', () => {
    expect(parsePtDate('15/10/2026')).toBe('2026-10-15');
    expect(parsePtDate(' 1/2/2026 ')).toBe('2026-02-01');
    expect(parsePtDate('29/02/2024')).toBe('2024-02-29');
  });

  it('is blank for an empty field', () => {
    expect(parsePtDate('')).toBe('');
    expect(parsePtDate('   ')).toBe('');
  });

  it.each(['32/13/2026', '31/04/2026', '29/02/2026', '00/10/2026', '15/00/2026', '15/10/26', '10/15/2026x', 'abc', '15/10/0999'])(
    'rejects %s',
    (text) => {
      expect(parsePtDate(text)).toBeNull();
    },
  );
});

describe('maskPtDate', () => {
  it('puts slashes between day, month and year as digits are typed', () => {
    expect(maskPtDate('1')).toBe('1');
    expect(maskPtDate('151')).toBe('15/1');
    expect(maskPtDate('15102026')).toBe('15/10/2026');
    expect(maskPtDate('151020261')).toBe('15/10/2026');
  });

  it('keeps the slashes the user types and drops anything else', () => {
    expect(maskPtDate('1/2/2026')).toBe('1/2/2026');
    expect(maskPtDate('15-10.2026')).toBe('15/10/2026');
    expect(maskPtDate('15/')).toBe('15/');
    expect(maskPtDate('1a5b')).toBe('15');
    expect(maskPtDate(maskPtDate('15102026'))).toBe('15/10/2026');
  });
});

describe('formatPtDate', () => {
  it('shows ISO dates as dd/mm/aaaa', () => {
    expect(formatPtDate('2026-10-15')).toBe('15/10/2026');
    expect(formatPtDate('2026-03-15T12:00:00Z')).toBe('15/03/2026');
    expect(formatPtDate('')).toBe('');
    expect(formatPtDate(null)).toBe('');
  });
});
