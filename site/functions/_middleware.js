import { blockedPath, notFound } from './guard.js';
import { withSecurity } from './security.js';

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
  return context.next();
}
