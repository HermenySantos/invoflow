/**
 * Scroll memory for AppLayout's #main-content, which scrolls instead of the window, so the
 * browser no longer restores the position on back, forward or reload. Keyed by pathname + search.
 */

const KEY_PREFIX = 'invoflow:scroll:';
/* Routes with a saved position, oldest first; outside KEY_PREFIX so it never reads as a route */
const ORDER_KEY = 'invoflow:scroll-order';
export const MAX_SAVED_ROUTES = 50;

let popstateRoute: string | null = null;
let requestedRoute: string | null = null;
let firstMount = true;

export function currentRoute(): string {
  return window.location.pathname + window.location.search;
}

if (typeof window !== 'undefined') {
  window.addEventListener('popstate', () => {
    popstateRoute = currentRoute();
  });
}

export function scrollKey(route: string): string {
  return KEY_PREFIX + route;
}

export function readScroll(route: string): number {
  try {
    const value = Number(sessionStorage.getItem(scrollKey(route)));
    return Number.isFinite(value) && value > 0 ? value : 0;
  } catch {
    return 0;
  }
}

function readOrder(): string[] {
  try {
    const order: unknown = JSON.parse(sessionStorage.getItem(ORDER_KEY) ?? '[]');
    return Array.isArray(order) ? order.filter((route): route is string => typeof route === 'string') : [];
  } catch {
    return [];
  }
}

/** Saves `top` for `route`, keeping only the MAX_SAVED_ROUTES most recently written routes. */
export function writeScroll(route: string, top: number): void {
  try {
    sessionStorage.setItem(scrollKey(route), String(Math.max(0, Math.round(top))));
    const order = readOrder();
    if (order[order.length - 1] === route) return;
    const next = order.filter((saved) => saved !== route);
    next.push(route);
    next.splice(0, next.length - MAX_SAVED_ROUTES).forEach((evicted) => sessionStorage.removeItem(scrollKey(evicted)));
    sessionStorage.setItem(ORDER_KEY, JSON.stringify(next));
  } catch {
    // Storage full or blocked: the position is just not remembered.
  }
}

/** Forgets every saved position (on sign-out, so the next account does not land mid-list). */
export function clearScrollMemory(): void {
  try {
    for (let i = sessionStorage.length - 1; i >= 0; i -= 1) {
      const key = sessionStorage.key(i);
      if (key?.startsWith(KEY_PREFIX)) sessionStorage.removeItem(key);
    }
    sessionStorage.removeItem(ORDER_KEY);
  } catch {
    // Storage blocked: nothing was saved.
  }
  popstateRoute = null;
  requestedRoute = null;
}

/** Makes the next push to `route` restore its saved position, like back would (the list after a save). */
export function requestScrollRestore(route: string): void {
  requestedRoute = route;
}

function pageLoadType(): string | undefined {
  if (typeof performance === 'undefined' || typeof performance.getEntriesByType !== 'function') return undefined;
  return (performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined)?.type;
}

/**
 * Whether the screen now mounting for `route` should get its saved position back: after back or
 * forward (popstate), after requestScrollRestore, or on the first screen after a reload. Any other
 * navigation starts at the top. Call once per mounted screen.
 */
export function takeRestoreDecision(route: string): boolean {
  const wasFirst = firstMount;
  firstMount = false;
  const popped = popstateRoute;
  const requested = requestedRoute;
  popstateRoute = null;
  requestedRoute = null;
  if (popped !== null) return popped === route;
  if (requested !== null) return requested === route;
  if (!wasFirst) return false;
  const type = pageLoadType();
  return type === 'reload' || type === 'back_forward';
}

export function resetScrollMemoryForTests(): void {
  popstateRoute = null;
  requestedRoute = null;
  firstMount = true;
}
