'use client';

import { ReactNode } from 'react';
import { BottomNav } from './BottomNav';
import { useAuth } from '@/components/providers/AuthProvider';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

interface AppLayoutProps {
  children: ReactNode;
  title?: string;
  showBack?: boolean;
}

export function AppLayout({ children, title }: AppLayoutProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/sign-in');
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-pulse">
          <div className="w-12 h-12 rounded-full bg-primary-200" />
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {title && (
        <header className="sticky top-0 z-40 bg-white border-b border-gray-200">
          <div className="flex items-center justify-center h-14 px-4">
            <h1 className="text-lg font-semibold text-gray-900">{title}</h1>
          </div>
        </header>
      )}
      <main className="max-w-lg mx-auto">{children}</main>
      <BottomNav />
    </div>
  );
}
