export const PT_DATE_PLACEHOLDER = 'dd/mm/aaaa';
export const PT_DATE_INVALID = 'Data inválida. Use dd/mm/aaaa.';

const SEPARATOR = /[/.\-\s]/;

/** Keeps what the user typed close to dd/mm/aaaa: digits only, a slash between parts, a 4-digit year. */
export function maskPtDate(raw: string): string {
  const parts = [''];
  for (const ch of raw) {
    let i = parts.length - 1;
    if (ch >= '0' && ch <= '9') {
      if (i < 2 && parts[i].length === 2) {
        parts.push('');
        i += 1;
      }
      if (i === 2 && parts[2].length >= 4) continue;
      parts[i] += ch;
    } else if (SEPARATOR.test(ch) && i < 2 && parts[i] !== '') {
      parts.push('');
    }
  }
  return parts.join('/');
}

/** dd/mm/aaaa (d/m also accepted) to yyyy-mm-dd; '' for blank, null when it is not a real date. */
export function parsePtDate(text: string): string | null {
  const trimmed = text.trim();
  if (trimmed === '') return '';
  const match = /^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$/.exec(trimmed);
  if (!match) return null;
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  if (year < 1900 || month < 1 || month > 12 || day < 1) return null;
  const check = new Date(Date.UTC(year, month - 1, day));
  if (check.getUTCMonth() !== month - 1 || check.getUTCDate() !== day) return null;
  return `${match[3]}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

/** yyyy-mm-dd (or a longer ISO timestamp) to dd/mm/aaaa; '' when there is no usable date. */
export function formatPtDate(iso: string | null | undefined): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  return match ? `${match[3]}/${match[2]}/${match[1]}` : '';
}
