const BLOCKED = new Set(['/.env', '/.git/config', '/admin', '/_routes.json']);

export function blockedPath(pathname) {
  return BLOCKED.has(pathname) || pathname.includes('//');
}

export function notFound() {
  return new Response('Not found\n', {
    status: 404,
    headers: {
      'content-type': 'text/plain; charset=utf-8',
      'cache-control': 'no-store',
      'x-content-type-options': 'nosniff',
    },
  });
}
