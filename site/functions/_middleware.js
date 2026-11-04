import { blockedPath, notFound } from './guard.js';
import { withSecurity, withoutSMaxAge } from './security.js';

function assetCatchAll(pathname) {
  return pathname === '/assets' || pathname.startsWith('/assets/');
}

async function missingPage(context) {
  const url = new URL(context.request.url);
  url.pathname = '/404.html';
  const asset = await context.env.ASSETS.fetch(new Request(url, { method: 'GET' }));
  const headers = withSecurity({
    'content-type': asset.headers.get('content-type') || 'text/html; charset=utf-8',
    'cache-control': 'no-store',
  });
  return new Response(context.request.method === 'HEAD' ? null : asset.body, { status: 404, headers });
}

export async function onRequest(context) {
  const path = new URL(context.request.url).pathname;
  if (blockedPath(path)) return notFound();
  if (path === '/404' || path === '/404.html') return missingPage(context);
  if (path === '/privacy') {
    return new Response(null, {
      status: 308,
      headers: withSecurity({
        location: '/privacy/',
        'cache-control': 'no-store',
      }),
    });
  }
  const response = await context.next();
  if (response.status === 404 || assetCatchAll(path)) return withoutSMaxAge(response);
  return response;
}
