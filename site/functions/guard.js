import { withSecurity, withoutSMaxAge } from './security.js';

const BLOCKED = new Set(['/.env', '/.git/config', '/admin', '/_routes.json']);

export function blockedPath(pathname) {
  return BLOCKED.has(pathname) || pathname.includes('//');
}

export function notFound() {
  return withoutSMaxAge(
    new Response('Not found\n', {
      status: 404,
      headers: withSecurity({
        'content-type': 'text/plain; charset=utf-8',
        'cache-control': 'no-store',
      }),
    }),
  );
}
