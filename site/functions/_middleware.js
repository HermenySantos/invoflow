import { blockedPath, notFound } from './guard.js';
import { withSecurity, withoutSMaxAge } from './security.js';

function assetCatchAll(pathname) {
  return pathname === '/assets' || pathname.startsWith('/assets/');
}

export async function onRequest(context) {
  const path = new URL(context.request.url).pathname;
  if (blockedPath(path)) return notFound();
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
