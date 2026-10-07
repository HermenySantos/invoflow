/*
 * FaturaFlow service worker: keeps the app shell available offline.
 *
 * Deliberately never caches /api/* or pages: those hold one user's receipts
 * and IVA figures, and a shared browser cache would show them to the next
 * person on the device. Only content-hashed build assets and a static
 * offline page are stored.
 */

const CACHE = 'faturaflow-shell-v1';
const PRECACHE = ['/offline.html', '/manifest.json', '/favicon.svg', '/icons/icon-192x192.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // One missing file must not stop the worker from installing.
      Promise.allSettled(PRECACHE.map((url) => cache.add(url)))
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return; // always the network, never stored

  // Build output is content-hashed, so a cached copy is never stale.
  if (url.pathname.startsWith('/_next/static/')) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(CACHE).then((cache) => cache.put(request, copy));
            }
            return response;
          })
      )
    );
    return;
  }

  // Pages come from the network; offline, show the static notice instead.
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match('/offline.html')));
  }
});
