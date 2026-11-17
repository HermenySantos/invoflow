'use client';

import { ReactNode, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { BottomNav } from './BottomNav';
import { MainScrollArea } from './MainScrollArea';
import { useAuth } from '@/components/providers/AuthProvider';

interface AppLayoutProps {
  children: ReactNode;
  title?: string;
}

export function AppLayout({ children, title }: AppLayoutProps) {
  const { isAuthenticated, isLoading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const next = pathname && pathname !== '/sign-in' ? `?next=${encodeURIComponent(pathname)}` : '';
      router.replace(`/sign-in${next}`);
    }
  }, [isAuthenticated, isLoading, pathname, router]);

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
    <div className="flex h-[100dvh] flex-col print:block print:h-auto">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-0 focus:left-0 focus:z-[100] focus:p-4 focus:bg-white focus:text-primary-600 focus:underline"
      >
        Saltar para o conteúdo
      </a>

      {title && (
        <header className="shrink-0 bg-[var(--ff-bg)] border-b border-[var(--ff-border)] safe-area-inset-top">
          <div className="flex items-center justify-between h-14 px-4 max-w-lg mx-auto">
            <h1 className="text-lg font-semibold">{title}</h1>
            <button
              type="button"
              onClick={() => {
                signOut();
                router.push('/');
              }}
              className="-mr-3 min-h-11 px-3 text-sm text-gray-500 touch-manipulation"
            >
              Sair
            </button>
          </div>
        </header>
      )}

      <MainScrollArea>{children}</MainScrollArea>

      <BottomNav />
    </div>
  );
}
