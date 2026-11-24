import { describe, it, expect, vi, afterEach } from 'vitest';
import { render } from '@testing-library/react';

// AppLayout sends signed-out users to /sign-in?next=<page>; with Clerk on, the Clerk
// <SignIn> must return there after sign-in (Clerk's own ?redirect_url= still wins).
const { signInProps, searchParams } = vi.hoisted(() => ({
  signInProps: vi.fn(),
  searchParams: { value: new URLSearchParams() },
}));
vi.mock('@clerk/nextjs', () => ({
  SignIn: (props: Record<string, unknown>) => {
    signInProps(props);
    return null;
  },
  useUser: () => ({ isLoaded: true, isSignedIn: false, user: null }),
  useClerk: () => ({ signOut: vi.fn() }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => searchParams.value,
  usePathname: () => '/sign-in',
}));

async function renderSignIn(query: string) {
  vi.resetModules();
  vi.stubEnv('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY', 'pk_test_dummy');
  searchParams.value = new URLSearchParams(query);
  const { default: SignInPage } = await import('@/app/sign-in/[[...sign-in]]/page');
  render(<SignInPage />);
  return signInProps.mock.calls.at(-1)?.[0] as Record<string, unknown>;
}

describe('Clerk sign-in redirect back', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    signInProps.mockReset();
  });

  it('returns to the page in ?next=', async () => {
    const props = await renderSignIn('next=%2Freceipts');
    expect(props.fallbackRedirectUrl).toBe('/receipts');
    expect(props.signUpUrl).toBe('/sign-up');
  });

  it('falls back to /upload for a missing or unsafe ?next=', async () => {
    expect((await renderSignIn('')).fallbackRedirectUrl).toBe('/upload');
    expect((await renderSignIn('next=%2F%2Fevil.com')).fallbackRedirectUrl).toBe('/upload');
  });
});
