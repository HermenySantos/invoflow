#!/usr/bin/env node
// Rasterises public/icons/*.svg into the PNG sizes the web manifest and iOS need.
// Run after editing an icon SVG: `CHROME=/path/to/chrome node scripts/generate-icons.mjs`.
// CHROME must be the browser binary itself: a wrapper that adds --remote-debugging-port never exits.
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const icons = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'icons');
const chrome = process.env.CHROME || 'google-chrome';

const outputs = [
  { svg: 'icon.svg', png: 'icon-192.png', size: 192 },
  { svg: 'icon.svg', png: 'icon-512.png', size: 512 },
  { svg: 'icon-maskable.svg', png: 'icon-maskable-192.png', size: 192 },
  { svg: 'icon-maskable.svg', png: 'icon-maskable-512.png', size: 512 },
  // iOS rounds the corners itself, so it gets the full-bleed artwork.
  { svg: 'icon-maskable.svg', png: 'apple-touch-icon.png', size: 180 },
];

const work = mkdtempSync(join(tmpdir(), 'invoflow-icons-'));
try {
  for (const { svg, png, size } of outputs) {
    const data = Buffer.from(readFileSync(join(icons, svg))).toString('base64');
    const page = join(work, `${png}.html`);
    writeFileSync(
      page,
      `<!doctype html><html><body style="margin:0;background:transparent">` +
        `<img src="data:image/svg+xml;base64,${data}" width="${size}" height="${size}" style="display:block">` +
        `</body></html>`
    );
    execFileSync(chrome, [
      '--headless=new',
      '--disable-gpu',
      '--hide-scrollbars',
      '--default-background-color=00000000',
      `--window-size=${size},${size}`,
      `--screenshot=${join(icons, png)}`,
      `file://${page}`,
    ], { stdio: 'ignore' });
    console.log(`${png} (${size}x${size})`);
  }
} finally {
  rmSync(work, { recursive: true, force: true });
}
