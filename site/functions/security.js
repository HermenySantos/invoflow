export const SECURITY_HEADERS = {
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'strict-origin-when-cross-origin',
  'permissions-policy': 'camera=(), microphone=(), geolocation=()',
  'x-frame-options': 'DENY',
  'strict-transport-security': 'max-age=31536000; includeSubDomains',
  'content-security-policy':
    "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; media-src 'self'; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'",
};

export function withSecurity(headers) {
  const next = new Headers(headers);
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) next.set(name, value);
  return next;
}

export function withoutSMaxAge(response) {
  const cache = response.headers.get('cache-control');
  if (!cache || !/s-maxage\s*=/i.test(cache)) return response;
  const headers = new Headers(response.headers);
  const cleaned = cache
    .split(',')
    .map((part) => part.trim())
    .filter((part) => part && !/^s-maxage\s*=/i.test(part))
    .join(', ');
  if (cleaned) headers.set('cache-control', cleaned);
  else headers.delete('cache-control');
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
