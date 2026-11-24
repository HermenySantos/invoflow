import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Regression: a full page load of /receipts right after sign-up sent GET /api/documents
// without a token (401), because the page fetches on mount before clerk-js has loaded and
// the client read window.Clerk.session too early. The client must wait for Clerk's token.
const { getTokenMock } = vi.hoisted(() => ({ getTokenMock: vi.fn() }));
vi.mock('@clerk/nextjs', () => ({ getToken: getTokenMock }));

function okJson() {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: () => Promise.resolve({ documents: [], total: 0, page: 1, page_size: 50, has_more: false }),
  };
}

async function loadApi() {
  vi.resetModules();
  return (await import('@/lib/api')).api;
}

describe('API client auth with Clerk', () => {
  beforeEach(() => {
    getTokenMock.mockReset();
    vi.stubEnv('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY', 'pk_test_dummy');
    global.fetch = vi.fn().mockResolvedValue(okJson());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    delete (window as unknown as { Clerk?: unknown }).Clerk;
  });

  it('waits for Clerk to load before the first request of a page, then sends the bearer token', async () => {
    // Full page load: clerk-js has not set window.Clerk (or its session) yet.
    delete (window as unknown as { Clerk?: unknown }).Clerk;
    let finishLoading!: (token: string) => void;
    getTokenMock.mockReturnValue(new Promise<string>((resolve) => { finishLoading = resolve; }));
    const api = await loadApi();

    const pending = api.getDocuments({ page_size: 50 });
    await new Promise((r) => setTimeout(r, 20));
    expect(global.fetch).not.toHaveBeenCalled();

    finishLoading('session-jwt');
    await pending;
    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('/api/documents?page_size=50');
    expect((init as RequestInit).headers).toMatchObject({ Authorization: 'Bearer session-jwt' });
  });

  it('does not send an unauthenticated request when Clerk cannot give a token', async () => {
    getTokenMock.mockRejectedValue(Object.assign(new Error('Timeout waiting for Clerk to load.'), { code: 'clerk_runtime_load_timeout' }));
    const api = await loadApi();

    await expect(api.getDocuments({ page_size: 50 })).rejects.toThrow('Timeout waiting for Clerk to load.');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('sends no Authorization header when Clerk says the user is signed out', async () => {
    getTokenMock.mockResolvedValue(null);
    const api = await loadApi();

    await api.getDocuments();
    const init = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1] as RequestInit;
    expect(init.headers).not.toHaveProperty('Authorization');
  });

  it('never asks Clerk for a token in demo mode', async () => {
    vi.stubEnv('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY', '');
    const api = await loadApi();

    await api.getDocuments();
    expect(getTokenMock).not.toHaveBeenCalled();
  });
});
