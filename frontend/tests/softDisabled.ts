import { expect } from 'vitest';

/**
 * Unavailable for a moment (request in flight, 429 wait) but still focusable, so keyboard focus
 * is not dropped to <body> when the wait starts (QA P-1). `disabled` would fail the focus check:
 * a disabled button cannot hold focus.
 */
export function expectWaiting(button: HTMLElement) {
  expect(button).toHaveAttribute('aria-disabled', 'true');
  expect(button).not.toHaveAttribute('disabled');
  button.focus();
  expect(document.activeElement).toBe(button);
}

/** Usable again: neither disabled nor aria-disabled. */
export function expectAvailable(button: HTMLElement) {
  expect(button).toBeEnabled();
  expect(button).not.toHaveAttribute('aria-disabled');
}
