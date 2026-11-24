import { describe, it, expect, vi, afterEach } from 'vitest';
import { NextRequest } from 'next/server';

// Regression (Crazy QA L-1): signed-out visits to protected pages went to Clerk's hosted
// Account Portal (accounts.invoflow.pt) because no sign-in URL was configured.
// Runs the real clerkMiddleware with a production-shaped key; a request with no Clerk
// cookies is signed out without any network call.
const PK = `pk_live_${Buffer.from('clerk.invoflow.pt$').toString('base64')}`;

async function runMiddleware(url: string, headers: Record<string, string> = {}) {
  vi.resetModules();
  vi.stubEnv('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY', PK);
  vi.stubEnv('CLERK_PUBLISHABLE_KEY', PK);
  vi.stubEnv('CLERK_SECRET_KEY', 'sk_live_dummy_for_tests');
  const { default: middleware } = await import('@/middleware');
  const request = new NextRequest(url, {
    headers: { accept: 'text/html', 'sec-fetch-dest': 'document', ...headers },
  });
  return (middleware as unknown as (r: NextRequest, e: unknown) => Promise<Response>)(request, {
    waitUntil: () => {},
  });
}

describe('middleware sign-in redirect', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('sends a signed-out visit to /upload to our /sign-in with a way back to /upload', async () => {
    const response = await runMiddleware('https://invoflow.pt/upload?x=1');
    expect([302, 307]).toContain(response.status);
    const location = new URL(response.headers.get('location')!, 'https://invoflow.pt');
    expect(location.origin).toBe('https://invoflow.pt');
    expect(location.pathname).toBe('/sign-in');
    expect(location.searchParams.get('redirect_url')).toBe('https://invoflow.pt/upload?x=1');
  });

  it('never points at the hosted Account Portal', async () => {
    const response = await runMiddleware('https://invoflow.pt/receipts');
    expect(response.headers.get('location') ?? '').not.toContain('accounts.');
  });

  it('leaves the public sign-in page alone', async () => {
    const response = await runMiddleware('https://invoflow.pt/sign-in');
    expect(response.headers.get('location')).toBeNull();
  });
});
