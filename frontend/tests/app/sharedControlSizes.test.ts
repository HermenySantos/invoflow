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

describe('danger button', () => {
  it('fills with --ff-danger #8b2e2e, darkens to #6f2424 on hover, and uses the 6 px radius', () => {
    expect(css).toMatch(/--ff-danger:\s*#8b2e2e;/);
    expect(css).toMatch(/--ff-danger-hover:\s*#6f2424;/);
    expect(css).toMatch(/--ff-radius:\s*6px;/);
    expect(applyOf('.btn-danger')).toEqual(expect.arrayContaining(['btn', 'text-white']));
    expect(css).toMatch(/\.btn-danger\s*\{[^}]*background:\s*var\(--ff-danger\);/);
    expect(css).toMatch(/\.btn-danger:hover\s*\{[^}]*background:\s*var\(--ff-danger-hover\);/);
    expect(css).toMatch(/\.btn\s*\{[^}]*border-radius:\s*var\(--ff-radius\);/);
  });
});
