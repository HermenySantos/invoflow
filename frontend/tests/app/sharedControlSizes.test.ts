import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const css = readFileSync(path.resolve(__dirname, '../../app/globals.css'), 'utf8');

function applyOf(selector: string): string[] {
  const block = css.match(new RegExp(`\\${selector}\\s*\\{[^}]*@apply([^;]*);`));
  expect(block, `${selector} has an @apply`).not.toBeNull();
  return block![1].trim().split(/\s+/);
}

describe('shared control classes', () => {
  it.each(['.input', '.btn-md'])('%s is 44 px tall below lg and keeps its desktop height from lg up', (selector) => {
    const classes = applyOf(selector);
    expect(classes).toContain('min-h-11');
    expect(classes).toContain('lg:min-h-0');
  });
});
