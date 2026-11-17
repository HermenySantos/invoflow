'use client';

import { ReactNode, useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { FOLD_CONTROLS, FOLD_COVER, foldGap, readScroll, takeRestoreDecision, writeScroll } from '@/lib/mainScroll';

const RESTORE_TIMEOUT_MS = 5000;
const USER_SCROLL_EVENTS = ['wheel', 'touchstart', 'pointerdown', 'keydown'] as const;

/** The app's only scroll area: between the header and BottomNav, with its position kept per route. */
export function MainScrollArea({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '';
  const mainRef = useRef<HTMLElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  /* Kept in a ref so Strict Mode's second effect run reuses the decision instead of taking a fresh one */
  const decision = useRef<{ pathname: string; restore: boolean } | null>(null);

  useEffect(() => {
    const main = mainRef.current;
    const content = contentRef.current;
    if (!main || !content) return;

    if (decision.current?.pathname !== pathname) {
      decision.current = { pathname, restore: takeRestoreDecision(pathname) };
    }
    const target = decision.current.restore ? readScroll(pathname) : 0;

    const updateFoldGap = () => {
      const current = parseFloat(main.style.marginBottom) || 0;
      const cover = content.querySelector(FOLD_COVER);
      const foldLine = main.getBoundingClientRect().bottom + current - (cover?.getBoundingClientRect().height ?? 0);
      const rects = Array.from(content.querySelectorAll(FOLD_CONTROLS))
        .filter((el) => !cover?.contains(el))
        .map((el) => el.getBoundingClientRect())
        .filter((r) => r.width > 1 && r.height > 1);
      const gap = foldGap(foldLine, rects);
      if (gap !== current) main.style.marginBottom = gap ? `${gap}px` : '';
    };

    let restoring = target > 0;
    let restoreFrame = 0;
    const started = Date.now();
    const stopRestoring = () => {
      if (!restoring) return;
      restoring = false;
      cancelAnimationFrame(restoreFrame);
      updateFoldGap();
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
      writeScroll(pathname, 0);
    }

    let saveFrame = 0;
    let unsavedTop: number | null = null;
    const save = () => {
      if (unsavedTop !== null) writeScroll(pathname, unsavedTop);
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

    updateFoldGap();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(updateFoldGap);
    observer?.observe(main);
    observer?.observe(content);

    return () => {
      restoring = false;
      cancelAnimationFrame(restoreFrame);
      cancelAnimationFrame(saveFrame);
      save();
      main.removeEventListener('scroll', onScroll);
      USER_SCROLL_EVENTS.forEach((type) => main.removeEventListener(type, stopRestoring));
      observer?.disconnect();
    };
  }, [pathname]);

  return (
    <main
      ref={mainRef}
      id="main-content"
      className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain print:!m-0 print:h-auto print:overflow-visible"
      tabIndex={-1}
    >
      {/* Bottom padding so the last row clears the nav */}
      <div ref={contentRef} className="max-w-lg mx-auto pb-4">
        {children}
      </div>
    </main>
  );
}
