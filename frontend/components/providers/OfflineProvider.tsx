'use client';

import { ReactNode, useEffect, useState } from 'react';
import { WifiOff } from 'lucide-react';

/**
 * Registers the service worker (production builds only: in dev it would
 * fight hot reload) and shows a banner while the device is offline.
 */
export function OfflineProvider({ children }: { children: ReactNode }) {
  const [isOnline, setIsOnline] = useState(true);

  useEffect(() => {
    if (process.env.NODE_ENV === 'production' && 'serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {
        // Offline support is a bonus; the app works without it.
      });
    }
  }, []);

  useEffect(() => {
    const update = () => setIsOnline(navigator.onLine);
    update();
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);

  return (
    <>
      {!isOnline && (
        <div
          role="status"
          className="fixed top-0 left-0 right-0 z-[100] flex items-center justify-center gap-2 bg-amber-500 px-4 py-2 text-sm font-medium text-white"
        >
          <WifiOff className="w-4 h-4" aria-hidden="true" />
          Sem ligação. Os dados mostrados podem não estar atualizados.
        </div>
      )}
      {children}
    </>
  );
}
