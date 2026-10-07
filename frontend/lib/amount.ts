/**
 * Parse an amount typed the Portuguese way ("1.234,56", "12,5") or the
 * English way ("1,234.56"). The last separator is the decimal one unless
 * exactly three digits follow it. Returns a "1234.56" string, or null.
 */
export function parseAmountInput(input: string): string | null {
  const cleaned = input.replace(/[\s€]/g, '');
  if (!/^\d[\d.,]*$/.test(cleaned)) return null;

  const last = Math.max(cleaned.lastIndexOf('.'), cleaned.lastIndexOf(','));
  if (last === -1) return Number(cleaned).toFixed(2);

  const integer = cleaned.slice(0, last).replace(/[.,]/g, '');
  const decimals = cleaned.slice(last + 1);
  const value = decimals.length === 3 ? Number(integer + decimals) : Number(`${integer}.${decimals || '0'}`);
  return Number.isFinite(value) ? value.toFixed(2) : null;
}
