import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  MAX_FOLD_GAP_PX,
  foldGap,
  readScroll,
  resetScrollMemoryForTests,
  scrollKey,
  takeRestoreDecision,
  writeScroll,
} from '@/lib/mainScroll';

function stubLoadType(type: string | undefined) {
  Object.defineProperty(performance, 'getEntriesByType', {
    configurable: true,
    value: vi.fn(() => (type ? [{ type }] : [])),
  });
}

describe('scroll memory', () => {
  beforeEach(() => {
    resetScrollMemoryForTests();
    sessionStorage.clear();
    stubLoadType('navigate');
  });

  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  it('stores the position per pathname', () => {
    writeScroll('/receipts', 1200.4);
    writeScroll('/summary', 900);
    expect(sessionStorage.getItem(scrollKey('/receipts'))).toBe('1200');
    expect(readScroll('/receipts')).toBe(1200);
    expect(readScroll('/summary')).toBe(900);
    expect(readScroll('/upload')).toBe(0);
  });

  it('reads 0 for a missing, negative or broken value', () => {
    sessionStorage.setItem(scrollKey('/a'), 'abc');
    sessionStorage.setItem(scrollKey('/b'), '-5');
    expect(readScroll('/a')).toBe(0);
    expect(readScroll('/b')).toBe(0);
  });

  it('starts a new navigation at the top', () => {
    expect(takeRestoreDecision('/receipts')).toBe(false);
    expect(takeRestoreDecision('/summary')).toBe(false);
  });

  it('restores on the first screen after a reload, and only that one', () => {
    stubLoadType('reload');
    expect(takeRestoreDecision('/receipts')).toBe(true);
    expect(takeRestoreDecision('/receipts/doc-1')).toBe(false);
  });

  it('restores on the first screen after a back/forward page load', () => {
    stubLoadType('back_forward');
    expect(takeRestoreDecision('/summary')).toBe(true);
  });

  it('restores the screen that back or forward (popstate) lands on, once', () => {
    takeRestoreDecision('/receipts');
    window.history.pushState(null, '', '/receipts');
    window.dispatchEvent(new PopStateEvent('popstate'));
    expect(takeRestoreDecision('/receipts')).toBe(true);
    expect(takeRestoreDecision('/summary')).toBe(false);
  });

  it('does not restore a different screen than the one popstate landed on', () => {
    takeRestoreDecision('/receipts');
    window.history.pushState(null, '', '/summary');
    window.dispatchEvent(new PopStateEvent('popstate'));
    expect(takeRestoreDecision('/receipts')).toBe(false);
  });
});

describe('foldGap', () => {
  it('is 0 when no control crosses the fold', () => {
    expect(foldGap(700, [{ top: 600, bottom: 644 }, { top: 700, bottom: 744 }, { top: 760, bottom: 804 }])).toBe(0);
  });

  it('raises the fold to the top of a control it cuts (the 44 px pencil at the fold)', () => {
    expect(foldGap(687, [{ top: 663, bottom: 707 }])).toBe(24);
  });

  it('keeps raising while the new fold cuts another control', () => {
    expect(foldGap(700, [{ top: 680, bottom: 724 }, { top: 660, bottom: 690 }])).toBe(40);
  });

  it('leaves a control taller than the cap alone', () => {
    expect(foldGap(700, [{ top: 700 - MAX_FOLD_GAP_PX - 1, bottom: 900 }])).toBe(0);
  });
});
