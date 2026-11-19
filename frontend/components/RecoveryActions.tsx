'use client';

import Link from 'next/link';
import { useAuth } from '@/components/providers/AuthProvider';

export const RECEIPTS_PATH = '/receipts';
export const SIGNED_OUT_RECEIPTS_PATH = `/sign-in?next=${RECEIPTS_PATH}`;

// Copy owned by the Conversion Lead (COPY-TOKENS-v1); change only with their sign-off.
export const NOT_FOUND_PRIMARY_LABEL = 'Ir para os recibos';
export const NOT_FOUND_SECONDARY_LABEL = 'Carregar um recibo';

export function receiptsHref(isAuthenticated: boolean): string {
  return isAuthenticated ? RECEIPTS_PATH : SIGNED_OUT_RECEIPTS_PATH;
}

export function NotFoundActions() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
      <Link
        href={receiptsHref(isAuthenticated)}
        className="btn-primary btn-md min-h-11 min-w-11 lg:min-h-11"
      >
        {NOT_FOUND_PRIMARY_LABEL}
      </Link>
      <Link
        href="/upload"
        className="inline-flex min-h-11 min-w-11 items-center justify-center px-4 font-medium text-[var(--ff-accent)] underline-offset-4 hover:underline focus:outline-none focus:ring-2 focus:ring-[var(--ff-accent)] focus:ring-offset-2"
        style={{ borderRadius: 'var(--ff-radius)' }}
      >
        {NOT_FOUND_SECONDARY_LABEL}
      </Link>
    </div>
  );
}
