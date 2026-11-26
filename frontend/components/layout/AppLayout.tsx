'use client';

import { ReactNode, useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { BottomNav } from './BottomNav';
import { LeftRail } from './LeftRail';
import { MainScrollArea } from './MainScrollArea';
import { useAuth } from '@/components/providers/AuthProvider';
import { reloadPage } from '@/lib/navigate';

/**
 * How long to wait for clerk-js before giving up on the spinner. A blocked or offline clerk-js
 * never finishes loading, which left protected pages on "A carregar…" forever (QA A-2). Clerk's
 * getToken gives up after 10 s, so by then nothing on the page can load either.
 */
export const AUTH_LOAD_TIMEOUT_MS = 15_000;

/** PT-PT copy pending Conversion Lead. */
export const AUTH_LOAD_FAILED = 'Não foi possível carregar a página.';
export const AUTH_LOAD_FAILED_HINT = 'Verifique a ligação à internet e tente de novo.';

function useTimedOut(active: boolean, ms: number) {
  const [timedOut, setTimedOut] = useState(false);
  useEffect(() => {
    if (!active) {
      setTimedOut(false);
      return;
    }
    const timer = setTimeout(() => setTimedOut(true), ms);
    return () => clearTimeout(timer);
  }, [active, ms]);
  return active && timedOut;
}

function AuthLoadFailed() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-sm text-center">
        <div role="alert">
          <p className="font-medium text-[var(--ff-text)]">{AUTH_LOAD_FAILED}</p>
          <p className="mt-1 text-sm text-[var(--ff-text-muted)]">{AUTH_LOAD_FAILED_HINT}</p>
        </div>
        <button type="button" onClick={reloadPage} className="btn-primary btn-md mt-4 min-h-11">
          Tentar de novo
        </button>
      </div>
    </div>
  );
}

interface AppLayoutProps {
  children: ReactNode;
  title?: string;
  /** Small label above the title. */
  eyebrow?: string;
}

export function AppLayout({ children, title, eyebrow }: AppLayoutProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const loadTimedOut = useTimedOut(isLoading, AUTH_LOAD_TIMEOUT_MS);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const next = pathname && pathname !== '/sign-in' ? `?next=${encodeURIComponent(pathname)}` : '';
      router.replace(`/sign-in${next}`);
    }
  }, [isAuthenticated, isLoading, pathname, router]);

  if (loadTimedOut) {
    return <AuthLoadFailed />;
  }

  if (isLoading) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        role="status"
        aria-label="A carregar"
      >
        <div className="text-sm text-gray-500">A carregar…</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    /* Only <main> scrolls and the nav sits below it in the flow, so no content can scroll under the nav */
    <div className="flex h-[100dvh] flex-col print:block print:h-auto lg:flex-row">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-0 focus:left-0 focus:z-[100] focus:p-4 focus:bg-white focus:text-primary-600 focus:underline"
      >
        Saltar para o conteúdo
      </a>

      <LeftRail />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {title && (
          <header className="shrink-0 border-b border-[var(--ff-border)] bg-[var(--ff-bg)] safe-area-inset-top">
            <div className="mx-auto flex min-h-14 w-full max-w-lg items-center justify-between px-4 py-1 md:max-w-3xl md:px-8 lg:mx-0 lg:max-w-4xl">
              <div>
                {eyebrow && (
                  <p className="text-xs font-medium uppercase tracking-wide text-[var(--ff-text-muted)]">{eyebrow}</p>
                )}
                <h1 className="text-lg font-semibold">{title}</h1>
              </div>
            </div>
          </header>
        )}

        <MainScrollArea>{children}</MainScrollArea>
      </div>

      <BottomNav />
    </div>
  );
}
