import { isValidElement, type ReactElement, type ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ptPT } from '@clerk/localizations';

const ClerkProvider = vi.fn(({ children }: { children: ReactNode }) => children);

vi.mock('@clerk/nextjs', () => ({
  ClerkProvider,
  useUser: () => ({ user: null, isLoaded: true, isSignedIn: false }),
  useClerk: () => ({ signOut: vi.fn() }),
}));
vi.mock('next/font/google', () => ({
  IBM_Plex_Sans: () => ({ variable: 'font-plex' }),
  Inter: () => ({ variable: 'font-inter' }),
}));

function findClerkProvider(node: ReactNode): ReactElement | null {
  if (!isValidElement(node)) return null;
  if (node.type === ClerkProvider) return node;
  const children = (node.props as { children?: ReactNode }).children;
  for (const child of Array.isArray(children) ? children : [children]) {
    const found = findClerkProvider(child);
    if (found) return found;
  }
  return null;
}

describe('Clerk sign-in and sign-up language', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('passes the European Portuguese localization to ClerkProvider', async () => {
    vi.stubEnv('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY', 'pk_test_placeholder');
    vi.resetModules();
    const { default: RootLayout } = await import('@/app/layout');

    const provider = findClerkProvider(RootLayout({ children: null }));

    expect(provider).not.toBeNull();
    expect((provider!.props as { localization?: unknown }).localization).toBe(ptPT);
    expect(ptPT.locale).toBe('pt-PT');
  });
});
