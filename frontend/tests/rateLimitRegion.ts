import { expect } from 'vitest';

/**
 * The 429 live region (W3C ARIA22): one role="status" node, mounted before any 429, so a screen
 * reader already knows it when the message lands in it.
 */
export function getRateLimitRegion(): HTMLElement {
  const regions = document.querySelectorAll<HTMLElement>('[data-testid="rate-limit-region"]');
  expect(regions).toHaveLength(1);
  const region = regions[0];
  expect(region).toHaveAttribute('role', 'status');
  expect(region).toHaveAttribute('aria-atomic', 'true');
  return region;
}

/** Present, not hidden, and silent: no text and no visible box. */
export function expectEmptyRegion(region: HTMLElement) {
  expect(region).toBeInTheDocument();
  expect(region.textContent).toBe('');
  expect(region.childElementCount).toBe(0);
  expect(region).not.toHaveAttribute('hidden');
  expect(region).not.toHaveAttribute('aria-hidden');
  expect(getComputedStyle(region).display).not.toBe('none');
}

/** The message is inside the region, with no second live region nested in it. */
export function expectRegionSays(region: HTMLElement, text: string) {
  expect(region).toHaveTextContent(text);
  expect(region.querySelector('[role="status"],[role="alert"],[aria-live]')).toBeNull();
}
