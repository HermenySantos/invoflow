import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearScrollMemory,
  currentRoute,
  MAX_SAVED_ROUTES,
  readScroll,
  requestScrollRestore,
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

function popstateTo(route: string) {
  window.history.pushState(null, '', route);
  window.dispatchEvent(new PopStateEvent('popstate'));
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

  it('keys the route by pathname and search', () => {
    window.history.replaceState(null, '', '/receipts?status=ready');
    expect(currentRoute()).toBe('/receipts?status=ready');
    writeScroll('/receipts?status=ready', 300);
    writeScroll('/receipts', 1200.4);
    expect(sessionStorage.getItem(scrollKey('/receipts'))).toBe('1200');
    expect(readScroll('/receipts?status=ready')).toBe(300);
    expect(readScroll('/receipts')).toBe(1200);
    expect(readScroll('/receipts?status=failed')).toBe(0);
  });

  it('reads 0 for a missing, negative or broken value', () => {
    sessionStorage.setItem(scrollKey('/a'), 'abc');
    sessionStorage.setItem(scrollKey('/b'), '-5');
    expect(readScroll('/a')).toBe(0);
    expect(readScroll('/b')).toBe(0);
  });

  it('forgets every saved position, and nothing else, on sign-out', () => {
    writeScroll('/receipts', 1200);
    writeScroll('/summary?period=2026-Q1', 900);
    sessionStorage.setItem('other', 'kept');
    requestScrollRestore('/receipts');
    clearScrollMemory();
    expect(readScroll('/receipts')).toBe(0);
    expect(readScroll('/summary?period=2026-Q1')).toBe(0);
    expect(sessionStorage.getItem('other')).toBe('kept');
    takeRestoreDecision('/upload');
    expect(takeRestoreDecision('/receipts')).toBe(false);
  });

  it(`keeps only the ${MAX_SAVED_ROUTES} most recently saved routes, evicting the oldest`, () => {
    for (let i = 0; i < MAX_SAVED_ROUTES + 5; i += 1) writeScroll(`/receipts/doc-${i}`, 100 + i);
    const savedKeys = Object.keys(sessionStorage).filter((key) => key.startsWith(scrollKey('')));
    expect(savedKeys).toHaveLength(MAX_SAVED_ROUTES);
    for (let i = 0; i < 5; i += 1) expect(sessionStorage.getItem(scrollKey(`/receipts/doc-${i}`))).toBeNull();
    expect(readScroll('/receipts/doc-5')).toBe(105);
    expect(readScroll(`/receipts/doc-${MAX_SAVED_ROUTES + 4}`)).toBe(MAX_SAVED_ROUTES + 104);
  });

  it('counts a rewrite as recent use, so an often-saved route is not evicted', () => {
    writeScroll('/receipts', 1200);
    for (let i = 0; i < MAX_SAVED_ROUTES - 1; i += 1) writeScroll(`/receipts/doc-${i}`, 10);
    writeScroll('/receipts', 1300);
    writeScroll('/summary', 50);
    expect(readScroll('/receipts')).toBe(1300);
    expect(readScroll('/summary')).toBe(50);
    expect(sessionStorage.getItem(scrollKey('/receipts/doc-0'))).toBeNull();
    expect(readScroll('/receipts/doc-1')).toBe(10);
  });

  it('recovers from a broken order list and clears it on sign-out', () => {
    sessionStorage.setItem('invoflow:scroll-order', '{not json');
    writeScroll('/receipts', 1200);
    expect(readScroll('/receipts')).toBe(1200);
    expect(JSON.parse(sessionStorage.getItem('invoflow:scroll-order')!)).toEqual(['/receipts']);
    clearScrollMemory();
    expect(sessionStorage.getItem('invoflow:scroll-order')).toBeNull();
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

  it('restores the route that back or forward (popstate) lands on, once', () => {
    takeRestoreDecision('/receipts/doc-1');
    popstateTo('/receipts?status=ready');
    expect(takeRestoreDecision('/receipts?status=ready')).toBe(true);
    expect(takeRestoreDecision('/receipts?status=ready')).toBe(false);
  });

  it('does not restore a route other than the one popstate landed on', () => {
    takeRestoreDecision('/receipts');
    popstateTo('/summary');
    expect(takeRestoreDecision('/receipts')).toBe(false);
  });

  it('restores the next push to a requested route (the list after a save), once', () => {
    takeRestoreDecision('/receipts/doc-1');
    requestScrollRestore('/receipts');
    expect(takeRestoreDecision('/receipts')).toBe(true);
    expect(takeRestoreDecision('/receipts')).toBe(false);
  });

  it('drops a restore request when another route mounts first', () => {
    takeRestoreDecision('/receipts/doc-1');
    requestScrollRestore('/receipts');
    expect(takeRestoreDecision('/summary')).toBe(false);
    expect(takeRestoreDecision('/receipts')).toBe(false);
  });
});
