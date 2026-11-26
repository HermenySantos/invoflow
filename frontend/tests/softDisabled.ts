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

/**
 * Held during a 429 wait: the visible text counts down, but the accessible name is the fixed
 * COPY-TOKENS-v1 §4a label, so a focused screen reader does not re-read it every second (UI Lead F-2).
 */
export function expectCountingDown(button: HTMLElement, seconds: number) {
  expectHeld(button);
  expect(button).toHaveAccessibleName('Tentar de novo (aguarde um momento)');
  expect(button).toHaveAccessibleName(RATE_LIMIT_BUTTON_LABEL);
  const visible = Array.from(button.querySelectorAll('[aria-hidden="true"]')).find((el) =>
    /Tentar de novo em \d+ s/.test(el.textContent ?? ''),
  );
  expect(visible?.textContent).toBe(`Tentar de novo em ${seconds} s`);
}

/** Usable again: neither disabled nor aria-disabled. */
export function expectAvailable(button: HTMLElement) {
  expect(button).toBeEnabled();
  expect(button).not.toHaveAttribute('aria-disabled');
}
