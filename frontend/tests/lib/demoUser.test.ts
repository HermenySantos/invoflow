import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { DEMO_AUTH_KEY, demoUserId, readDemoUser } from '@/lib/demoUser';

// Node's own (empty) localStorage global hides jsdom's, so use an in-memory one.
function memoryStorage(): Storage {
  const items = new Map<string, string>();
  return {
    get length() { return items.size; },
    clear: () => items.clear(),
    getItem: (key) => items.get(key) ?? null,
    key: (index) => Array.from(items.keys())[index] ?? null,
    removeItem: (key) => { items.delete(key); },
    setItem: (key, value) => { items.set(key, String(value)); },
  };
}

describe('demo users', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', memoryStorage());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('gives each email its own stable id', () => {
    expect(demoUserId('ana@empresa.pt')).toBe(demoUserId(' Ana@Empresa.pt '));
    expect(demoUserId('ana@empresa.pt')).not.toBe(demoUserId('rui@empresa.pt'));
    expect(demoUserId('ana@empresa.pt')).toMatch(/^demo-[0-9a-f]{8}$/);
  });

  it('upgrades sessions saved with the old shared id', () => {
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: 'mock-user-001', email: 'ana@empresa.pt' }));
    expect(readDemoUser()?.id).toBe(demoUserId('ana@empresa.pt'));
  });

  it('sends the demo id with API requests', async () => {
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify({ id: '', email: 'ana@empresa.pt' }));
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ documents: [] }),
    });
    global.fetch = fetchMock;

    await api.getDocuments();

    const headers = fetchMock.mock.calls[0][1].headers;
    expect(headers['X-Mock-User-Id']).toBe(demoUserId('ana@empresa.pt'));
  });
});
