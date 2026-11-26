import { readFileSync } from 'node:fs';
import path from 'node:path';
import postcss from 'postcss';
import tailwindcss from 'tailwindcss';
import { beforeAll, describe, expect, it } from 'vitest';
import tailwindConfig from '../../tailwind.config';

/**
 * The compiled CSS, as the browser gets it. A busy button (aria-disabled, see lib/softDisabled.ts)
 * keeps focus, so its focus ring must stay visible (UI Lead F-1) and hover must not pretend it is
 * clickable (N-3).
 */
let compiled: postcss.Root;
const rules: { selector: string; decls: Record<string, string> }[] = [];

beforeAll(async () => {
  const source = readFileSync(path.resolve(__dirname, '../../app/globals.css'), 'utf8');
  const result = await postcss([tailwindcss({ ...tailwindConfig, content: [{ raw: '<button class="btn btn-primary btn-secondary btn-danger btn-accent-outline btn-ghost-danger">', extension: 'html' }] })]).process(source, {
    from: path.resolve(__dirname, '../../app/globals.css'),
  });
  compiled = result.root;
  compiled.walkRules((rule) => {
    const decls: Record<string, string> = {};
    rule.walkDecls((d) => {
      decls[d.prop] = d.value;
    });
    rules.push({ selector: rule.selector, decls });
  });
});

function rulesFor(test: (selector: string) => boolean) {
  return rules.filter((r) => r.selector.split(',').some((s) => test(s.trim())));
}

describe('busy (aria-disabled) buttons', () => {
  it('fade to 50% at rest but only to 75% when keyboard-focused, so the ring keeps its contrast', () => {
    const rest = rulesFor((s) => s === '.btn[aria-disabled="true"]').filter((r) => r.decls.opacity);
    expect(rest.map((r) => r.decls.opacity)).toContain('0.5');
    const focused = rulesFor((s) => s === '.btn:focus-visible[aria-disabled="true"]').filter((r) => r.decls.opacity);
    expect(focused.map((r) => r.decls.opacity)).toContain('0.75');
  });

  it('gives the secondary button the same strong focus ring as primary', () => {
    // Later rules win at equal specificity, so the last ring colour is the one the browser paints.
    const ring = (selector: string) =>
      rulesFor((s) => s === `${selector}:focus`)
        .map((r) => r.decls['--tw-ring-color'])
        .filter(Boolean)
        .at(-1);
    expect(ring('.btn-secondary')).toBeDefined();
    expect(ring('.btn-secondary')).toBe(ring('.btn-primary'));
  });

  it.each(['.btn-primary', '.btn-danger', '.btn-secondary', '.btn-accent-outline', '.btn-ghost-danger'])(
    '%s changes colour on hover only when it is not aria-disabled',
    (selector) => {
      const hovers = rulesFor((s) => s.startsWith(`${selector}:hover`));
      expect(hovers.length).toBeGreaterThan(0);
      for (const r of hovers) {
        for (const s of r.selector.split(',').map((x) => x.trim()).filter((x) => x.startsWith(`${selector}:hover`))) {
          expect(s).toBe(`${selector}:hover:not([aria-disabled="true"])`);
        }
      }
    },
  );
});
