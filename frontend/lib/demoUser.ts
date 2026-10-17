/**
 * Demo sign-in (no Clerk key): each email gets its own stable user id, which
 * the API client sends as X-Mock-User-Id so the backend keeps data apart.
 */

export const DEMO_AUTH_KEY = 'invoflow_mock_auth';

const DEMO_ON = new Set(['1', 'true', 'yes', 'on']);

/** Demo copy needs the explicit flag and no Clerk publishable key. */
export function isDemoModeEnabled(
  env: Record<string, string | undefined> = process.env,
): boolean {
  const demo = DEMO_ON.has(String(env.NEXT_PUBLIC_DEMO_AUTH ?? '').trim().toLowerCase());
  const key = String(env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? '').trim();
  return demo && key.length === 0;
}

export const isDemoMode = isDemoModeEnabled();

export interface DemoUser {
  id: string;
  email: string;
}

/** Stable id for an email: "demo-" + FNV-1a hash, so the same email always gets the same data. */
export function demoUserId(email: string): string {
  let hash = 0x811c9dc5;
  for (const char of email.trim().toLowerCase()) {
    hash ^= char.codePointAt(0)!;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return `demo-${hash.toString(16).padStart(8, '0')}`;
}

export function readDemoUser(): DemoUser | null {
  try {
    const stored = localStorage.getItem(DEMO_AUTH_KEY);
    if (!stored) return null;
    const { email } = JSON.parse(stored) as DemoUser;
    // Recompute: sessions saved before ids were per-email all say "mock-user-001".
    return { id: demoUserId(email), email };
  } catch {
    return null;
  }
}
