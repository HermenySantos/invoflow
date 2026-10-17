import { describe, expect, it } from 'vitest';
import { safeNextPath } from '@/lib/safeNext';

describe('safeNextPath', () => {
  it('allows a same-origin relative path', () => {
    expect(safeNextPath('/upload')).toBe('/upload');
    expect(safeNextPath('/receipts/abc?tab=1')).toBe('/receipts/abc?tab=1');
    expect(safeNextPath('/')).toBe('/');
  });

  it('rejects protocol-relative, backslash, scheme and encoded forms', () => {
    expect(safeNextPath('//example.org/phish')).toBe('/upload');
    expect(safeNextPath('/\\example.org')).toBe('/upload');
    expect(safeNextPath('https://example.org/phish')).toBe('/upload');
    expect(safeNextPath('http://example.org')).toBe('/upload');
    expect(safeNextPath('/%2F%2Fexample.org/phish')).toBe('/upload');
    expect(safeNextPath('/%5Cexample.org')).toBe('/upload');
    expect(safeNextPath('/%2f%2fexample.org')).toBe('/upload');
    expect(safeNextPath('javascript:alert(1)')).toBe('/upload');
    expect(safeNextPath(null)).toBe('/upload');
    expect(safeNextPath('')).toBe('/upload');
  });
});
