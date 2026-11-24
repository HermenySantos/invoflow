'use client';

import { ReactNode, useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { currentRoute, readScroll, takeRestoreDecision, writeScroll } from '@/lib/mainScroll';

const RESTORE_TIMEOUT_MS = 5000;
const USER_SCROLL_EVENTS = ['wheel', 'touchstart', 'pointerdown', 'keydown'] as const;

/** The app's only scroll area: between the header and BottomNav, with its position kept per route. */
export function MainScrollArea({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const mainRef = useRef<HTMLElement>(null);
  /* Kept in a ref so Strict Mode's second effect run reuses the decision instead of taking a fresh one */
  const decision = useRef<{ route: string; restore: boolean } | null>(null);

  useEffect(() => {
    const main = mainRef.current;
    if (!main) return;

    /* Read from location rather than useSearchParams, which would need a Suspense boundary on every static page */
    const route = currentRoute();
    if (decision.current?.route !== route) {
      decision.current = { route, restore: takeRestoreDecision(route) };
    }
    const target = decision.current.restore ? readScroll(route) : 0;

    let restoring = target > 0;
    let restoreFrame = 0;
    const started = Date.now();
    const stopRestoring = () => {
      restoring = false;
      cancelAnimationFrame(restoreFrame);
    };
    const restore = () => {
      main.scrollTop = target;
      if (Math.abs(main.scrollTop - target) < 1 || Date.now() - started > RESTORE_TIMEOUT_MS) stopRestoring();
      else restoreFrame = requestAnimationFrame(restore);
    };
    if (restoring) {
      restore();
    } else {
      main.scrollTop = 0;
      writeScroll(route, 0);
    }

    let saveFrame = 0;
    let unsavedTop: number | null = null;
    const save = () => {
      if (unsavedTop !== null) writeScroll(route, unsavedTop);
      unsavedTop = null;
    };
    const onScroll = () => {
      if (restoring) return;
      unsavedTop = main.scrollTop;
      cancelAnimationFrame(saveFrame);
      saveFrame = requestAnimationFrame(save);
    };
    main.addEventListener('scroll', onScroll, { passive: true });
    USER_SCROLL_EVENTS.forEach((type) => main.addEventListener(type, stopRestoring, { passive: true }));

    return () => {
      stopRestoring();
      cancelAnimationFrame(saveFrame);
      save();
      main.removeEventListener('scroll', onScroll);
      USER_SCROLL_EVENTS.forEach((type) => main.removeEventListener(type, stopRestoring));
    };
  }, [pathname]);

  return (
    <main
      ref={mainRef}
      id="main-content"
      className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain print:h-auto print:overflow-visible"
      tabIndex={-1}
    >
      {/* Bottom padding so the last row clears the nav at the end of the scroll */}
      <div className="mx-auto w-full max-w-lg pb-4 md:max-w-3xl md:px-8 lg:mx-0 lg:max-w-4xl">{children}</div>
    </main>
  );
}
