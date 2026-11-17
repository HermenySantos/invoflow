import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MainScrollArea } from '@/components/layout/MainScrollArea';
import { resetScrollMemoryForTests, scrollKey } from '@/lib/mainScroll';

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

  it('restores the saved position after a reload', () => {
    Object.defineProperty(performance, 'getEntriesByType', { configurable: true, value: () => [{ type: 'reload' }] });
    pathnameMock.mockReturnValue('/summary');
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

describe('MainScrollArea fold guard', () => {
  beforeEach(() => {
    resetScrollMemoryForTests();
    pathnameMock.mockReturnValue('/summary');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('ends the scroll area above a control the fold would cut, so it is fully below the fold', () => {
    const rect = (top: number, bottom: number) => ({ top, bottom, left: 0, right: 44, width: 44, height: bottom - top, x: 0, y: top, toJSON: () => ({}) });
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      if (this.tagName === 'MAIN') return rect(57, 687 - (parseFloat(this.style.marginBottom) || 0)) as DOMRect;
      if (this.tagName === 'BUTTON') return rect(663, 707) as DOMRect;
      return rect(0, 0) as DOMRect;
    });
    renderArea();
    expect(screen.getByRole('main').style.marginBottom).toBe('24px');
  });

  it("takes a sticky bottom bar's top as the fold and ignores the controls behind it", () => {
    const rect = (top: number, bottom: number) => ({ top, bottom, left: 0, right: 44, width: 44, height: bottom - top, x: 0, y: top, toJSON: () => ({}) });
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      const gap = parseFloat(screen.getByRole('main').style.marginBottom) || 0;
      if (this.tagName === 'MAIN') return rect(0, 719 - gap) as DOMRect;
      if (this.dataset.foldCover !== undefined) return rect(599 - gap, 719 - gap) as DOMRect;
      if (this.getAttribute('aria-label') === 'Behind the bar') return rect(650, 694) as DOMRect;
      if (this.getAttribute('aria-label') === 'At the bar edge') return rect(580, 624) as DOMRect;
      if (this.getAttribute('aria-label') === 'Está correto') return rect(650 - gap, 694 - gap) as DOMRect;
      return rect(0, 0) as DOMRect;
    });
    render(
      <MainScrollArea>
        <input aria-label="At the bar edge" />
        <input aria-label="Behind the bar" />
        <div data-fold-cover>
          <button type="button">Está correto</button>
        </div>
      </MainScrollArea>,
    );
    expect(screen.getByRole('main').style.marginBottom).toBe('19px');
  });

  it('adds no gap when nothing crosses the fold', () => {
    renderArea();
    expect(screen.getByRole('main').style.marginBottom).toBe('');
  });
});
