const FALLBACK = '/upload';

/** Same-origin relative path. Rejects schemes, //, backslashes and encoded forms of those. */
export function safeNextPath(next: string | null | undefined, fallback = FALLBACK): string {
  if (next == null) return fallback;
  let value = next.trim();
  if (!value) return fallback;
  try {
    for (let i = 0; i < 3; i += 1) {
      const decoded = decodeURIComponent(value);
      if (decoded === value) break;
      value = decoded;
    }
  } catch {
    return fallback;
  }
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) {
    return fallback;
  }
  if (value.includes('\\') || value.includes('\0') || /\s/.test(value)) {
    return fallback;
  }
  const pathOnly = value.split('?')[0].split('#')[0];
  if (pathOnly.includes(':')) return fallback;
  return value;
}
