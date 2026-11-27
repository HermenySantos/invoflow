import { expect } from 'vitest';
import { RATE_LIMIT_BUTTON_LABEL } from '@/lib/rateLimitCopy';

/**
 * Unavailable for a moment (request in flight, 429 wait) and focus survived the change (QA P-1, W-15).
 * Callers focus the button BEFORE the state change; this only reads document.activeElement.
 * A `disabled` button fails here: it cannot hold focus.
 */
export function expectHeld(button: HTMLElement) {
  expect(button).toHaveAttribute('aria-disabled', 'true');
  expect(button).not.toHaveAttribute('disabled');
  expect(document.activeElement).toBe(button);
}

/** Text drawn on screen: everything except sr-only (aria-hidden text is still painted). */
export function visibleText(el: HTMLElement): string {
  const copy = el.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('.sr-only').forEach((n) => n.remove());
  return copy.textContent ?? '';
}

/** Visible text that is also exposed to assistive tech: the "label" WCAG 2.5.3 wants inside the name. */
function visibleLabel(el: HTMLElement): string {
  const copy = el.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('.sr-only, [aria-hidden="true"]').forEach((n) => n.remove());
  return (copy.textContent ?? '').trim();
}

/**
 * Held during a 429 wait. The visible text counts down, but the accessible name is the fixed
 * COPY-TOKENS-v1 §4a token, so a focused screen reader does not re-read it every second (UI Lead F-2).
 * The name comes from content, never aria-label, and starts with the visible label (R2-1, WCAG 2.5.3).
 */
export function expectCountingDown(button: HTMLElement, seconds: number) {
  expectHeld(button);
  expect(button).toHaveAccessibleName('Tentar de novo (aguarde um momento)');
  expect(button).toHaveAccessibleName(RATE_LIMIT_BUTTON_LABEL);
  expect(button).not.toHaveAttribute('aria-label');
  expect(button).not.toHaveAttribute('aria-labelledby');
  expect(button.querySelector('[aria-label],[aria-labelledby]')).toBeNull();
  expect(visibleText(button)).toBe(`Tentar de novo em ${seconds} s`);
  expect(visibleLabel(button)).toBe('Tentar de novo');
  expect(RATE_LIMIT_BUTTON_LABEL.startsWith(visibleLabel(button))).toBe(true);
}

/** Usable again: neither disabled nor aria-disabled. */
export function expectAvailable(button: HTMLElement) {
  expect(button).toBeEnabled();
  expect(button).not.toHaveAttribute('aria-disabled');
}
