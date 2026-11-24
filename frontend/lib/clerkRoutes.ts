/**
 * Our own pt-PT sign-in and sign-up pages. Without these, Clerk sends signed-out visits to
 * protected pages to its hosted Account Portal (accounts.invoflow.pt) instead.
 */
export const CLERK_SIGN_IN_URL = '/sign-in';
export const CLERK_SIGN_UP_URL = '/sign-up';

export const CLERK_MIDDLEWARE_OPTIONS = {
  signInUrl: CLERK_SIGN_IN_URL,
  signUpUrl: CLERK_SIGN_UP_URL,
} as const;
