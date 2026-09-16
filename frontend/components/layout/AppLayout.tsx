'use client';

import { ReactNode, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { BottomNav } from './BottomNav';
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
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-sm text-gray-500">A carregar…</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen pb-20">
      {title && (
        <header className="sticky top-0 z-40 bg-[var(--ff-bg)] border-b border-[var(--ff-border)]">
          <div className="flex items-center justify-between h-14 px-4 max-w-lg mx-auto">
            <h1 className="text-lg font-semibold">{title}</h1>
            <button
              type="button"
              onClick={() => {
                signOut();
                router.push('/');
              }}
              className="text-sm text-gray-500"
            >
              Sair
            </button>
          </div>
        </header>
      )}
      <main className="max-w-lg mx-auto">{children}</main>
      <BottomNav />
    </div>
  );
}
