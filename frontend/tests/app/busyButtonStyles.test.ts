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

const source = readFileSync(path.resolve(__dirname, '../../app/globals.css'), 'utf8');

function hex(value: string): [number, number, number] {
  const m = value.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
  if (m) return [1, 2, 3].map((i) => parseInt(m[i], 16)) as [number, number, number];
  const rgb = value.match(/^rgb\((\d+) (\d+) (\d+)/);
  expect(rgb, `colour ${value}`).not.toBeNull();
  return [1, 2, 3].map((i) => Number(rgb![i])) as [number, number, number];
}
function cssVar(name: string): [number, number, number] {
  const m = source.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6});`, 'i'));
  expect(m, name).not.toBeNull();
  return hex(m![1]);
}
const over = (fg: number[], bg: number[], alpha: number) => fg.map((c, i) => Math.round(c * alpha + bg[i] * (1 - alpha)));
function luminance(rgb: number[]) {
  const [r, g, b] = rgb.map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: number[], b: number[]) {
  const [lo, hi] = [luminance(a), luminance(b)].sort((x, y) => x - y);
  return (hi + 0.05) / (lo + 0.05);
}

describe('busy (aria-disabled) buttons', () => {
  it('fade to 50% at rest but only to 75% when keyboard-focused, so the ring keeps its contrast', () => {
    const rest = rulesFor((s) => s === '.btn[aria-disabled="true"]').filter((r) => r.decls.opacity);
    expect(rest.map((r) => r.decls.opacity)).toContain('0.5');
    const focused = rulesFor((s) => s === '.btn:focus-visible[aria-disabled="true"]').filter((r) => r.decls.opacity);
    expect(focused.map((r) => r.decls.opacity)).toContain('0.75');
  });

  it.each(['.btn-primary', '.btn-secondary'])(
    '%s keeps a focus ring of at least 3:1 against the page and the white offset while aria-disabled (WCAG 1.4.11)',
    (selector) => {
      const opacity = Number(
        rulesFor((s) => s === '.btn:focus-visible[aria-disabled="true"]')
          .map((r) => r.decls.opacity)
          .filter(Boolean)
          .at(-1),
      );
      const ring = rulesFor((s) => s === `${selector}:focus`)
        .map((r) => r.decls['--tw-ring-color'])
        .filter(Boolean)
        .at(-1)!;
      // The whole button, ring and offset included, is painted at `opacity` over what is behind it.
      for (const behind of [cssVar('--ff-bg'), cssVar('--ff-surface')]) {
        const paintedRing = over(hex(ring), behind, opacity);
        const paintedOffset = over([255, 255, 255], behind, opacity);
        expect(contrast(paintedRing, behind)).toBeGreaterThanOrEqual(3);
        expect(contrast(paintedRing, paintedOffset)).toBeGreaterThanOrEqual(3);
      }
    },
  );

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
