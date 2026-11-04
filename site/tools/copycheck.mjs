// Every PT and EN string in copy.js must appear verbatim in COPY-v4 and the v4.3 labels.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { copy } from '../public/js/copy.js';

const here = dirname(fileURLToPath(import.meta.url));

function norm(value) {
  return String(value)
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

const dropped = ['faq8Q', 'faq8A', 'faq8Link', 'tokHosting'];

export function missingCopy() {
  const doc = norm(
    `${readFileSync(join(here, 'copy/COPY-v4.md'), 'utf8')}\n${readFileSync(join(here, 'copy/COPY-v4-ui-labels.md'), 'utf8')}`.replace(/\*\*/g, ''),
  );
  const miss = { pt: [], en: [] };
  for (const lang of ['pt', 'en']) {
    for (const key of dropped) {
      if (Object.hasOwn(copy[lang], key)) miss[lang].push(`${key}: FAQ 8 was dropped from v1`);
    }
    for (const [key, value] of Object.entries(copy[lang])) {
      if (typeof value !== 'string' || dropped.includes(key)) continue;
      if (!doc.includes(norm(value))) miss[lang].push(`${key}: ${norm(value)}`);
    }
  }
  return miss;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const miss = missingCopy();
  console.log(JSON.stringify({ missingInCopy: miss }, null, 1));
  if (miss.pt.length || miss.en.length) process.exit(1);
}
