/**
 * Scroll memory and fold guard for AppLayout's #main-content, which scrolls instead of the window,
 * so the browser no longer restores the position on back, forward or reload.
 */

const KEY_PREFIX = 'invoflow:scroll:';

/** A control taller than this cut by the fold is left as is, so the gap above the nav stays small. */
export const MAX_FOLD_GAP_PX = 96;

export const FOLD_CONTROLS = 'a[href], button, input, select, textarea, [role="button"]';

/** A bar stuck to the bottom of the scroll area (the receipt's action bar): the fold is its top edge. */
export const FOLD_COVER = '[data-fold-cover]';

let popstatePath: string | null = null;
let firstMount = true;

if (typeof window !== 'undefined') {
  window.addEventListener('popstate', () => {
    popstatePath = window.location.pathname;
  });
}

export function scrollKey(pathname: string): string {
  return KEY_PREFIX + pathname;
}

export function readScroll(pathname: string): number {
  try {
    const value = Number(sessionStorage.getItem(scrollKey(pathname)));
    return Number.isFinite(value) && value > 0 ? value : 0;
  } catch {
    return 0;
  }
}

export function writeScroll(pathname: string, top: number): void {
  try {
    sessionStorage.setItem(scrollKey(pathname), String(Math.max(0, Math.round(top))));
  } catch {
    // Storage full or blocked: the position is just not remembered.
  }
}

function pageLoadType(): string | undefined {
  if (typeof performance === 'undefined' || typeof performance.getEntriesByType !== 'function') return undefined;
  return (performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined)?.type;
}

/**
 * Whether the screen now mounting for `pathname` should get its saved position back: after back or
 * forward (popstate), or on the first screen after a reload. A new navigation starts at the top.
 * Call once per mounted screen.
 */
export function takeRestoreDecision(pathname: string): boolean {
  const wasFirst = firstMount;
  firstMount = false;
  if (popstatePath !== null) {
    const matches = popstatePath === pathname;
    popstatePath = null;
    return matches;
  }
  if (!wasFirst) return false;
  const type = pageLoadType();
  return type === 'reload' || type === 'back_forward';
}

export function resetScrollMemoryForTests(): void {
  popstatePath = null;
  firstMount = true;
}

/**
 * How far to raise the bottom edge of the scroll area so no control is cut by it: the edge moves
 * up to the top of any control it crosses, until it crosses none. 0 when that exceeds `maxGap`.
 */
export function foldGap(
  foldLine: number,
  controls: ReadonlyArray<{ top: number; bottom: number }>,
  maxGap: number = MAX_FOLD_GAP_PX,
): number {
  let line = foldLine;
  let moved = true;
  while (moved) {
    moved = false;
    for (const { top, bottom } of controls) {
      if (top < line && bottom > line) {
        line = top;
        moved = true;
      }
    }
  }
  const gap = foldLine - line;
  return gap <= maxGap ? gap : 0;
}
