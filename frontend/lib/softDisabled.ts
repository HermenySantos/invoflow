import type { MouseEvent } from 'react';

/**
 * Props for a button that is unavailable only for a moment (a request in flight, a 429 wait) and
 * must keep keyboard focus while it is. `disabled` drops focus to <body> the moment it applies, so a
 * keyboard or screen-reader user who pressed the button loses their place (QA P-1). `aria-disabled`
 * keeps the button focusable and announced as unavailable; while it is set, a click (mouse, Enter or
 * Space) is stopped in the capture phase, so the button's own onClick never runs and a surrounding
 * form is never submitted.
 *
 * Usage: `<button {...softDisabled(busy)} onClick={save}>`. Keep `disabled` for states the user
 * leaves by changing something else (a missing choice).
 */
export function softDisabled(unavailable: boolean) {
  return {
    'aria-disabled': unavailable ? (true as const) : undefined,
    onClickCapture: (event: MouseEvent<HTMLElement>) => {
      if (!unavailable) return;
      event.preventDefault();
      event.stopPropagation();
    },
  };
}
