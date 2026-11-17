import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MainScrollArea } from '@/components/layout/MainScrollArea';
import { requestScrollRestore, resetScrollMemoryForTests, scrollKey, takeRestoreDecision } from '@/lib/mainScroll';

const { pathnameMock } = vi.hoisted(() => ({ pathnameMock: vi.fn(() => '/receipts') }));

vi.mock('next/navigation', () => ({
  usePathname: () => pathnameMock(),
}));

/**
 * jsdom does no layout: cap #main-content's scrollTop at `max.value`, which the test grows like
 * content loading in. Patched on the prototype because the restore starts as soon as <main> mounts.
 */
function limitMainScroll(max: { value: number }): () => void {
  const original = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollTop')!;
  const tops = new WeakMap<Element, number>();
  Object.defineProperty(Element.prototype, 'scrollTop', {
    configurable: true,
    get(this: Element) {
      return this.id === 'main-content' ? tops.get(this) ?? 0 : original.get!.call(this);
    },
    set(this: Element, value: number) {
      if (this.id === 'main-content') tops.set(this, Math.max(0, Math.min(value, max.value)));
      else original.set!.call(this, value);
    },
  });
  return () => Object.defineProperty(Element.prototype, 'scrollTop', original);
}

const nextFrame = () => act(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));

function popstateTo(pathname: string) {
  window.history.pushState(null, '', pathname);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function renderArea() {
  return render(
    <MainScrollArea>
      <button type="button">Editar IVA vendas</button>
    </MainScrollArea>,
  );
}

describe('MainScrollArea scroll position', () => {
  beforeEach(() => {
    resetScrollMemoryForTests();
    sessionStorage.clear();
    pathnameMock.mockReturnValue('/receipts');
    window.history.replaceState(null, '', '/receipts');
    Object.defineProperty(performance, 'getEntriesByType', { configurable: true, value: () => [{ type: 'navigate' }] });
  });

  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  it('starts a forward navigation at the top and forgets the old position for that route', () => {
    sessionStorage.setItem(scrollKey('/receipts'), '1200');
    renderArea();
    expect(screen.getByRole('main').scrollTop).toBe(0);
    expect(sessionStorage.getItem(scrollKey('/receipts'))).toBe('0');
  });

  it('saves the position on scroll, per route', async () => {
    renderArea();
    const main = screen.getByRole('main');
    main.scrollTop = 1200;
    main.dispatchEvent(new Event('scroll'));
    await waitFor(() => expect(sessionStorage.getItem(scrollKey('/receipts'))).toBe('1200'));
    expect(sessionStorage.getItem(scrollKey('/summary'))).toBeNull();
  });

  it('saves a pending position when the route unmounts before the next frame', () => {
    const { unmount } = renderArea();
    const main = screen.getByRole('main');
    main.scrollTop = 640;
    main.dispatchEvent(new Event('scroll'));
    unmount();
    expect(sessionStorage.getItem(scrollKey('/receipts'))).toBe('640');
  });

  it('restores the saved position after back (popstate)', () => {
    sessionStorage.setItem(scrollKey('/receipts'), '1200');
    popstateTo('/receipts');
    renderArea();
    expect(screen.getByRole('main').scrollTop).toBe(1200);
  });

  it('keys the position by pathname and search', async () => {
    window.history.replaceState(null, '', '/receipts?status=ready');
    sessionStorage.setItem(scrollKey('/receipts'), '1200');
    renderArea();
    const main = screen.getByRole('main');
    main.scrollTop = 300;
    main.dispatchEvent(new Event('scroll'));
    await waitFor(() => expect(sessionStorage.getItem(scrollKey('/receipts?status=ready'))).toBe('300'));
    expect(sessionStorage.getItem(scrollKey('/receipts'))).toBe('1200');
  });

  it('restores the list on the push after a save (requestScrollRestore), and keeps its saved position', () => {
    takeRestoreDecision('/receipts/doc-14');
    sessionStorage.setItem(scrollKey('/receipts'), '1200');
    requestScrollRestore('/receipts');
    renderArea();
    expect(screen.getByRole('main').scrollTop).toBe(1200);
    expect(sessionStorage.getItem(scrollKey('/receipts'))).toBe('1200');
  });

  it('restores the saved position after a reload', () => {
    Object.defineProperty(performance, 'getEntriesByType', { configurable: true, value: () => [{ type: 'reload' }] });
    pathnameMock.mockReturnValue('/summary');
    window.history.replaceState(null, '', '/summary');
    sessionStorage.setItem(scrollKey('/summary'), '900');
    renderArea();
    expect(screen.getByRole('main').scrollTop).toBe(900);
  });

  it('keeps trying until the content is tall enough, without saving the partial position', async () => {
    sessionStorage.setItem(scrollKey('/receipts'), '1200');
    popstateTo('/receipts');
    const max = { value: 0 };
    const unlimit = limitMainScroll(max);
    try {
      renderArea();
      const main = screen.getByRole('main');
      expect(main.scrollTop).toBe(0);
      max.value = 400;
      await nextFrame();
      expect(main.scrollTop).toBe(400);
      main.dispatchEvent(new Event('scroll'));
      await nextFrame();
      expect(sessionStorage.getItem(scrollKey('/receipts'))).toBe('1200');
      max.value = 5000;
      await waitFor(() => expect(main.scrollTop).toBe(1200));
    } finally {
      unlimit();
    }
  });

  it('stops restoring once the user scrolls', async () => {
    sessionStorage.setItem(scrollKey('/receipts'), '1200');
    popstateTo('/receipts');
    const max = { value: 300 };
    const unlimit = limitMainScroll(max);
    try {
      renderArea();
      const main = screen.getByRole('main');
      expect(main.scrollTop).toBe(300);
      main.dispatchEvent(new Event('touchstart'));
      max.value = 5000;
      await nextFrame();
      await nextFrame();
      expect(main.scrollTop).toBe(300);
    } finally {
      unlimit();
    }
  });
});
