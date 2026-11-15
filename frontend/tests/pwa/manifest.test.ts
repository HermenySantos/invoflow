import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import manifest from '@/app/manifest';
import { config as middlewareConfig } from '@/middleware';

const root = path.resolve(__dirname, '../..');
const publicFile = (url: string) => path.join(root, 'public', url);

function pngSize(file: string) {
  const png = readFileSync(file);
  expect(png.subarray(1, 4).toString('ascii')).toBe('PNG');
  return `${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`;
}

function cssToken(name: string) {
  const css = readFileSync(path.join(root, 'app/globals.css'), 'utf8');
  return css.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`))![1].toLowerCase();
}

describe('web manifest', () => {
  const m = manifest();

  it('describes a standalone PT-PT app', () => {
    expect(m.name).toBe('Invoflow');
    expect(m.short_name).toBe('Invoflow');
    expect(m.lang).toBe('pt-PT');
    expect(m.display).toBe('standalone');
    expect(m.description).toBeTruthy();
  });

  it('uses the design colours', () => {
    expect(m.theme_color!.toLowerCase()).toBe(cssToken('--ff-accent'));
    expect(m.background_color!.toLowerCase()).toBe(cssToken('--ff-bg'));
  });

  it('starts on an app route inside its scope, as do its shortcuts', () => {
    const routes = [m.start_url!, ...(m.shortcuts ?? []).map((s) => s.url)];
    for (const url of routes) {
      expect(url.startsWith(m.scope!)).toBe(true);
      expect(existsSync(path.join(root, 'app', url, 'page.tsx'))).toBe(true);
    }
  });

  it('ships regular and maskable PNG icons at 192 and 512 px', () => {
    const icons = m.icons ?? [];
    for (const purpose of ['any', 'maskable']) {
      for (const size of ['192x192', '512x512']) {
        const icon = icons.find((i) => i.purpose === purpose && i.sizes === size && i.type === 'image/png');
        expect(icon, `${purpose} ${size}`).toBeDefined();
      }
    }
    for (const icon of icons) {
      const file = publicFile(icon.src);
      expect(existsSync(file), icon.src).toBe(true);
      if (icon.type === 'image/png') expect(pngSize(file), icon.src).toBe(icon.sizes);
    }
  });

  it('gives every shortcut a 96 px icon that exists', () => {
    for (const shortcut of m.shortcuts ?? []) {
      const icon = shortcut.icons?.find((i) => i.sizes === '96x96');
      expect(icon, shortcut.name).toBeDefined();
      expect(pngSize(publicFile(icon!.src))).toBe('96x96');
    }
  });

  it('lists only raster icons, which Chrome can decode for install', () => {
    expect((m.icons ?? []).every((i) => i.type === 'image/png')).toBe(true);
  });

  it('has an apple-touch-icon at 180 px', () => {
    expect(pngSize(publicFile('/icons/apple-touch-icon.png'))).toBe('180x180');
  });
});

describe('auth middleware', () => {
  // Matchers are path-to-regexp patterns that are also valid regular expressions.
  const matchers = middlewareConfig.matcher.map((pattern) => new RegExp(`^${pattern}$`));
  const intercepted = (pathname: string) => matchers.some((re) => re.test(pathname));

  it('lets the browser fetch the install files without signing in', () => {
    for (const pathname of [
      '/manifest.webmanifest',
      '/sw.js',
      '/offline.html',
      '/favicon.svg',
      '/icons/icon-192.png',
      '/icons/icon-maskable-512.png',
      '/icons/apple-touch-icon.png',
    ]) {
      expect(intercepted(pathname), pathname).toBe(false);
    }
  });

  it('still protects app pages and the API', () => {
    expect(intercepted('/receipts')).toBe(true);
    expect(intercepted('/api/documents')).toBe(true);
  });
});
