import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const ORIGIN = 'https://app.invoflow.test';
const source = readFileSync(path.resolve(__dirname, '../../public/sw.js'), 'utf8');

type FakeRequest = { url: string; method: string; mode: string };
type Listener = (event: Record<string, unknown>) => void;

function request(pathOrUrl: string, init: Partial<FakeRequest> = {}): FakeRequest {
  return { url: new URL(pathOrUrl, ORIGIN).href, method: 'GET', mode: 'cors', ...init };
}

const keyOf = (req: FakeRequest | string) => new URL(typeof req === 'string' ? req : req.url, ORIGIN).href;

/** Runs public/sw.js against an in-memory Cache Storage and a scriptable network. */
function loadWorker() {
  const listeners: Record<string, Listener> = {};
  const stores = new Map<string, Map<string, Response>>();
  let online = true;
  const network = vi.fn(async (req: FakeRequest | string) => {
    if (!online) throw new TypeError('Failed to fetch');
    const url = new URL(keyOf(req));
    if (url.pathname.endsWith('/missing.js')) return new Response('nope', { status: 404 });
    return new Response(`body of ${url.pathname}`, { status: 200 });
  });

  const openStore = (name: string) => {
    if (!stores.has(name)) stores.set(name, new Map());
    const store = stores.get(name)!;
    return {
      add: async (url: string) => {
        const response = await network(url);
        if (!response.ok) throw new TypeError('bad response');
        store.set(keyOf(url), response);
      },
      put: async (req: FakeRequest | string, response: Response) => {
        store.set(keyOf(req), response);
      },
    };
  };

  const caches = {
    open: async (name: string) => openStore(name),
    keys: async () => [...stores.keys()],
    delete: async (name: string) => stores.delete(name),
    match: async (req: FakeRequest | string) => {
      for (const store of stores.values()) {
        const hit = store.get(keyOf(req));
        if (hit) return hit.clone();
      }
      return undefined;
    },
  };

  const self = {
    location: new URL(`${ORIGIN}/sw.js`),
    addEventListener: (type: string, fn: Listener) => {
      listeners[type] = fn;
    },
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn(async () => undefined) },
  };

  new Function('self', 'caches', 'fetch', 'Response', source)(self, caches, network, Response);

  async function lifecycle(type: 'install' | 'activate') {
    let pending: Promise<unknown> = Promise.resolve();
    listeners[type]({ waitUntil: (p: Promise<unknown>) => (pending = p) });
    await pending;
  }

  /** Returns the response the worker chose, or null when it left the request to the browser. */
  async function dispatch(req: FakeRequest): Promise<Response | null> {
    let responded: Promise<Response> | null = null;
    listeners.fetch({ request: req, respondWith: (p: Promise<Response>) => (responded = p) });
    const response = responded ? await responded : null;
    await new Promise((resolve) => setTimeout(resolve, 0)); // let fire-and-forget cache writes land
    return response;
  }

  const cachedPaths = () =>
    [...stores.values()].flatMap((store) => [...store.keys()].map((key) => new URL(key).pathname));

  return {
    stores,
    network,
    lifecycle,
    dispatch,
    cachedPaths,
    goOffline: () => {
      online = false;
    },
  };
}

describe('service worker', () => {
  let sw: ReturnType<typeof loadWorker>;

  beforeEach(async () => {
    sw = loadWorker();
    await sw.lifecycle('install');
  });

  it('precaches only the offline page, the manifest and the icons', () => {
    expect(sw.cachedPaths().sort()).toEqual([
      '/favicon.svg',
      '/icons/icon-192.png',
      '/icons/icon-512.png',
      '/icons/icon-maskable-192.png',
      '/icons/icon-maskable-512.png',
      '/manifest.webmanifest',
      '/offline.html',
    ]);
  });

  it('drops caches left by an older worker on activate', async () => {
    sw.stores.set('invoflow-shell-v1', new Map([[`${ORIGIN}/old.js`, new Response('old')]]));
    await sw.lifecycle('activate');
    expect([...sw.stores.keys()]).toEqual(['invoflow-shell-v2']);
  });

  it('leaves API calls to the browser and never stores them', async () => {
    expect(await sw.dispatch(request('/api/documents?quarter=2026-Q1'))).toBeNull();
    expect(await sw.dispatch(request('/api/documents/abc', { mode: 'navigate' }))).toBeNull();
    expect(await sw.dispatch(request('/api/documents/abc', { method: 'PATCH' }))).toBeNull();
    expect(sw.cachedPaths().some((p) => p.startsWith('/api/'))).toBe(false);
  });

  it('ignores other origins and non-GET requests', async () => {
    expect(await sw.dispatch(request('https://clerk.example.com/v1/client'))).toBeNull();
    expect(await sw.dispatch(request('/_next/static/chunks/app.js', { method: 'POST' }))).toBeNull();
  });

  it('serves pages from the network and does not keep a copy', async () => {
    const response = await sw.dispatch(request('/receipts/abc', { mode: 'navigate' }));
    expect(await response!.text()).toBe('body of /receipts/abc');
    expect(sw.cachedPaths()).not.toContain('/receipts/abc');
  });

  it('leaves in-app data requests (React Server Component fetches) to the browser', async () => {
    expect(await sw.dispatch(request('/summary?_rsc=1a2b'))).toBeNull();
    expect(sw.cachedPaths()).not.toContain('/summary');
  });

  it('shows the offline page when a navigation fails', async () => {
    sw.goOffline();
    const response = await sw.dispatch(request('/receipts', { mode: 'navigate' }));
    expect(await response!.text()).toBe('body of /offline.html');
  });

  it('caches hashed build assets after the first load and serves them offline', async () => {
    const asset = request('/_next/static/chunks/app-3f9a.js');
    await sw.dispatch(asset);
    expect(sw.cachedPaths()).toContain('/_next/static/chunks/app-3f9a.js');

    sw.goOffline();
    const response = await sw.dispatch(asset);
    expect(await response!.text()).toBe('body of /_next/static/chunks/app-3f9a.js');
  });

  it('does not cache a failed build asset response', async () => {
    const response = await sw.dispatch(request('/_next/static/chunks/missing.js'));
    expect(response!.status).toBe(404);
    expect(sw.cachedPaths()).not.toContain('/_next/static/chunks/missing.js');
  });
});
