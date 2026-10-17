import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CONFIG } from './js/config.js';
import { copy } from './js/copy.js';
import { isQualified, parseAnswers, readUtm } from './js/qualify.js';
import { onRequestPost } from './functions/api/signup.js';
import { captionFiles } from './tools/captions.mjs';

const root = dirname(fileURLToPath(import.meta.url));
const read = (path) => readFileSync(join(root, path), 'utf8');

const pages = ['index.html', 'privacy/index.html', 'js/copy.js', 'js/main.js', 'css/site.css'].map(read);
const visible = pages.join('\n');

const banned = [
  /accountant-ready/i,
  /pronto para o contabilista/i,
  /a pagar/i,
  /caf[eé]/i,
  /restaurante/i,
  /\bTODO\b/,
  /a confirmar/i,
  /\bprazo\b/i,
  /\d{1,2}\s+de\s+(janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)/i,
];

for (const pattern of banned) {
  assert.equal(pattern.test(visible), false, `banned copy ${pattern}`);
}

const amounts = [...visible.matchAll(/€\s*(\d+)|(\d+)\s*€/g)].map((match) => match[1] || match[2]);
assert.deepEqual([...new Set(amounts)].sort(), ['19', '190']);

const home = read('index.html');
for (const key of ['heroTitle', 'heroSub', 'priceLine', 'cta', 'caveat']) {
  assert.ok(home.includes(copy.pt[key]), key);
}
assert.ok(home.includes('href="/privacy"'));
assert.ok(home.includes('rel="canonical" href="https://invoflow.pt/"'));
assert.ok(home.includes('property="og:url" content="https://invoflow.pt/"'));
assert.ok(home.includes('pack para enviar ao seu contabilista'));
assert.equal((home.match(/exemplo ilustrativo/g) || []).length, 0);

const privacy = read('privacy/index.html');
assert.ok(privacy.includes('href="/"'));
assert.ok(privacy.includes('Hermenegildo Jerónimo dos Santos'));
assert.ok(privacy.includes('hermeny7@hotmail.com'));
assert.ok(privacy.includes('É uma estimativa. Este valor ignora o IVA das vendas.'));
assert.ok(privacy.includes('rel="canonical" href="https://invoflow.pt/privacy"'));
assert.ok(privacy.includes('property="og:url" content="https://invoflow.pt/privacy"'));

const sitemap = read('sitemap.xml');
assert.ok(sitemap.includes('<loc>https://invoflow.pt/</loc>'));
assert.ok(sitemap.includes('<loc>https://invoflow.pt/privacy</loc>'));
assert.ok(read('robots.txt').includes('Sitemap: https://invoflow.pt/sitemap.xml'));

assert.equal(CONFIG.FORM_ENDPOINT, '');
assert.equal(CONFIG.DEPOSIT_ENABLED, false);
assert.equal(CONFIG.STRIPE_PAYMENT_LINK, '');
assert.equal(CONFIG.ANALYTICS, '');
assert.equal(CONFIG.META_PIXEL_ID, '');

const qualified = { regime: 'trimestral', volume: '20-100', accountant: 'sim' };
assert.equal(isQualified(qualified), true);
assert.equal(isQualified({ ...qualified, volume: 'gt100' }), true);
assert.equal(isQualified({ ...qualified, volume: 'lt20' }), false);
assert.equal(isQualified({ ...qualified, regime: 'mensal' }), false);
assert.equal(isQualified({ ...qualified, regime: 'nao_sei' }), false);
assert.equal(isQualified({ ...qualified, accountant: 'nao' }), false);
assert.equal(isQualified({ ...qualified, consent: false }), true);

const base = { ...qualified, name: 'Ana Costa', email: 'ana@example.com', consent: true };
assert.equal(parseAnswers(base).qualified, true);
assert.equal(parseAnswers({ ...base, consent: false }), null);
assert.equal(parseAnswers({ ...base, email: 'not-an-email' }), null);
assert.equal(parseAnswers({ ...base, regime: 'mensal' }).qualified, false);

const params = new URLSearchParams('utm_source=meta&utm_medium=cpc&utm_campaign=pilot&utm_term=ignore');
assert.deepEqual(readUtm(params), {
  utm_source: 'meta',
  utm_medium: 'cpc',
  utm_campaign: 'pilot',
});

const ruleHits = read('js/qualify.js').match(/regime === 'trimestral'/g) || [];
assert.equal(ruleHits.length, 1);
const elsewhere = ['index.html', 'js/main.js', 'js/copy.js', 'functions/api/signup.js']
  .map(read)
  .join('\n');
assert.equal(elsewhere.includes("regime === 'trimestral'"), false);

const visitor = [home, read('js/copy.js'), read('js/main.js')].join('\n');
for (const phrase of [
  'Os lugares no piloto são limitados',
  'Pilot places are limited',
  'O que a página promete',
  'What this page promises',
  'Endpoint por configurar',
  'Endpoint not configured',
]) {
  assert.equal(visitor.includes(phrase), false, phrase);
}
assert.ok(visitor.includes('O que recebe'));
assert.ok(visitor.includes('What you get'));
assert.ok(visitor.includes('Inscrições abrem em breve.'));
assert.ok(visitor.includes('Registration opens soon.'));
assert.match(home, /id="submit-pilot"[^>]*disabled/);

const captions = `${read('assets/captions-pt.vtt')}\n${read('assets/captions-en.vtt')}`;
assert.equal(/prazo de pagamento/i.test(captions), false);
assert.equal(/continente/i.test(captions), false);
assert.match(read('assets/captions-pt.vtt'), /Prazo de entrega: 20 de Maio de 2026/);
assert.match(read('assets/captions-pt.vtt'), /Prazo de entrega: 22 de Fevereiro de 2027/);
assert.match(read('assets/captions-pt.vtt'), /exemplo ilustrativo/i);
assert.match(read('assets/captions-pt.vtt'), /IVA estimativa 23,00 €/);
assert.match(read('assets/captions-pt.vtt'), /NIF 999 999 990/);
assert.match(read('assets/captions-en.vtt'), /Filing deadline: 20 May 2026/);
assert.match(read('assets/captions-en.vtt'), /Filing deadline: 22 February 2027/);

const validBody = {
  ...base,
  utm_source: 'meta',
  utm_medium: 'cpc',
  utm_campaign: 'pilot',
  qualified: false,
};

const missing = await onRequestPost({
  request: new Request('https://pilot.test/api/signup', {
    method: 'POST',
    body: JSON.stringify({ email: 'ana@example.com' }),
  }),
  env: {},
});
assert.equal(missing.status, 400);

const unbound = await onRequestPost({
  request: new Request('https://pilot.test/api/signup', {
    method: 'POST',
    body: JSON.stringify(validBody),
  }),
  env: {},
});
assert.equal(unbound.status, 501);

const savedKv = memoryKv();
const saved = await post(
  { ...validBody, regime: 'mensal', qualified: true },
  { SIGNUPS: savedKv },
  { 'cf-connecting-ip': '198.51.100.4' },
);
assert.equal(saved.status, 200);
const stored = kvSignups(savedKv)[0];
assert.equal(stored.qualified, false);
assert.equal(stored.utm_source, 'meta');
assert.equal(Object.hasOwn(stored, 'password'), false);

await assertSignupGuards('kv', () => {
  const kv = memoryKv();
  return { env: { SIGNUPS: kv }, list: () => kvSignups(kv), rates: () => kvRateRows(kv) };
});
await assertSignupGuards('d1', () => {
  const db = memoryDb();
  return {
    env: { DB: db },
    list: () => db.signups.map((row) => JSON.parse(row.payload)),
    rates: () => db.rates,
  };
});

const homeSource = read('index.html');
assert.match(homeSource, /class="honeypot"[\s\S]*name="leave_blank"/);
assert.match(homeSource, /id="leave_blank"[^>]*type="text"/);
assert.match(read('js/main.js'), /leave_blank: form\.leave_blank\.value/);
assert.match(read('css/site.css'), /\.honeypot\s*\{/);
assert.match(read('privacy/index.html'), /O endereço IP não é guardado\./);
assert.match(read('privacy/index.html'), /The IP address is not stored\./);

const timeline = JSON.parse(read('assets/demo-timeline.json'));
const duration = mp4DurationSeconds(join(root, 'assets/demo-short.mp4'));
assert.ok(duration > 0, 'mp4 duration');
const ptCues = parseVtt(read('assets/captions-pt.vtt'));
const enCues = parseVtt(read('assets/captions-en.vtt'));
assert.deepEqual(
  ptCues.map((cue) => [cue.start, cue.end]),
  enCues.map((cue) => [cue.start, cue.end]),
);
for (const cue of [...ptCues, ...enCues]) {
  assert.ok(cue.start < cue.end, `cue order ${cue.start}`);
  assert.ok(cue.end <= duration, `cue ends ${cue.end} after video ${duration}`);
  assert.ok(cue.end <= 17.5, `cue ends ${cue.end} after 17.5s`);
}
const review = timeline.find((item) => item.name === 'review');
const q4 = timeline.find((item) => item.name === 'deadline-q4');
for (const cue of ptCues) {
  if (cue.end <= review.start / 1000 + 0.001) assert.equal(/NIF/i.test(cue.text), false);
}
for (const cue of enCues) {
  if (cue.end <= review.start / 1000 + 0.001) assert.equal(/NIF/i.test(cue.text), false);
}
const nifCue = ptCues.find((cue) => /NIF 999 999 990/.test(cue.text));
assert.ok(nifCue.start >= review.start / 1000 - 0.001);
const q4Cue = ptCues.find((cue) => cue.text.includes('22 de Fevereiro de 2027'));
assert.ok(Math.abs(q4Cue.start - q4.start / 1000) < 0.05);
assert.ok(Math.abs(q4Cue.end - q4.end / 1000) < 0.05);
const expectedCaptions = captionFiles(timeline);
assert.equal(read('assets/captions-pt.vtt'), expectedCaptions.pt);
assert.equal(read('assets/captions-en.vtt'), expectedCaptions.en);

for (const code of ['pt-PT', 'en', 'x-default']) {
  assert.match(homeSource, new RegExp(`<link rel="alternate" hreflang="${code}" href="https://invoflow.pt/"\\s*/>`));
  assert.match(
    read('privacy/index.html'),
    new RegExp(`<link rel="alternate" hreflang="${code}" href="https://invoflow.pt/privacy"\\s*/>`),
  );
}

const headerFile = read('_headers');
assert.match(headerFile, /^ {2}Strict-Transport-Security: max-age=31536000; includeSubDomains$/m);
assert.equal(/preload/i.test(headerFile), false);

console.log('site checks passed');

function memoryKv() {
  const rows = new Map();
  const puts = [];
  return {
    rows,
    puts,
    async get(key) {
      return rows.has(key) ? rows.get(key) : null;
    },
    async put(key, value, opts) {
      rows.set(key, value);
      puts.push({ key, value, opts });
    },
  };
}

function kvSignups(kv) {
  const records = [];
  for (const value of kv.rows.values()) {
    try {
      const parsed = JSON.parse(value);
      if (parsed && typeof parsed === 'object' && typeof parsed.email === 'string') records.push(parsed);
    } catch {
      continue;
    }
  }
  return records;
}

function kvRateRows(kv) {
  const rates = new Map();
  for (const [key, value] of kv.rows) {
    if (!key.startsWith('rate:')) continue;
    rates.set(key.slice('rate:'.length), JSON.parse(value));
  }
  return rates;
}

function memoryDb() {
  const signups = [];
  const rates = new Map();
  return {
    signups,
    rates,
    prepare(sql) {
      const text = sql.replace(/\s+/g, ' ').trim();
      return {
        bind(...args) {
          return {
            async first() {
              if (text.startsWith('SELECT count, reset_at FROM signup_rates')) {
                const row = rates.get(args[0]);
                return row ? { count: row.count, reset_at: row.resetAt } : null;
              }
              if (text.startsWith('SELECT id FROM signups')) {
                const found = signups.find((row) => row.email === args[0]);
                return found ? { id: found.id } : null;
              }
              throw new Error(`unexpected read ${text}`);
            },
            async run() {
              if (text.startsWith('INSERT INTO signup_rates')) {
                rates.set(args[0], { count: args[1], resetAt: args[2] });
                return {};
              }
              if (text.startsWith('UPDATE signup_rates')) {
                const row = rates.get(args[1]);
                row.count = args[0];
                return {};
              }
              if (text.startsWith('INSERT INTO signups')) {
                if (signups.some((row) => row.email === args[1])) {
                  throw new Error('UNIQUE constraint failed: signups.email');
                }
                signups.push({ id: args[0], email: args[1], payload: args[2], receivedAt: args[3] });
                return {};
              }
              throw new Error(`unexpected write ${text}`);
            },
          };
        },
      };
    },
  };
}

function post(body, env, headers = {}) {
  return onRequestPost({
    request: new Request('https://pilot.test/api/signup', {
      method: 'POST',
      headers: { 'content-type': 'application/json', ...headers },
      body: typeof body === 'string' ? body : JSON.stringify(body),
    }),
    env,
  });
}

async function sha256(value) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function assertSignupGuards(label, open) {
  const { env, list, rates } = open();
  const ip = '198.51.100.10';
  const headers = { 'cf-connecting-ip': ip };
  const honeypot = await post({ leave_blank: 'https://spam.example' }, env, headers);
  assert.equal(honeypot.status, 200, label);
  assert.deepEqual(await honeypot.json(), { ok: true });
  assert.equal(list().length, 0, label);

  const emptyHoneypot = await post(
    { ...validBody, email: 'empty-hp@example.com', leave_blank: '   ' },
    env,
    { 'cf-connecting-ip': '198.51.100.40' },
  );
  assert.equal(emptyHoneypot.status, 200, label);
  const kept = list().find((record) => record.email === 'empty-hp@example.com');
  assert.ok(kept, label);
  assert.equal(Object.hasOwn(kept, 'leave_blank'), false);

  const first = await post(
    { ...validBody, email: '  Ana@Example.com ', password: 'secret' },
    env,
    { 'cf-connecting-ip': '198.51.100.41' },
  );
  assert.equal(first.status, 200, label);
  const again = await post(
    { ...validBody, name: 'Outra Pessoa', email: 'ana@example.com' },
    env,
    { 'cf-connecting-ip': '198.51.100.42' },
  );
  assert.equal(again.status, 200, label);
  assert.deepEqual(await again.json(), { ok: true });
  const duplicates = list().filter((record) => record.email === 'ana@example.com');
  assert.equal(duplicates.length, 1, label);
  assert.equal(duplicates[0].name, 'Ana Costa');
  assert.equal(Object.hasOwn(duplicates[0], 'password'), false);

  for (let index = 0; index < 5; index += 1) {
    const response = await post({ ...validBody, email: `quota-${label}-${index}@example.com` }, env, headers);
    assert.equal(response.status, 200, `${label} ${index}`);
  }
  const beforeBlock = list().length;
  const blocked = await post({ ...validBody, email: `quota-${label}-blocked@example.com` }, env, headers);
  assert.equal(blocked.status, 429, label);
  assert.equal(list().length, beforeBlock, label);

  const other = await post(
    { ...validBody, email: `other-${label}@example.com` },
    env,
    { 'cf-connecting-ip': '198.51.100.11' },
  );
  assert.equal(other.status, 200, label);

  const hash = await sha256(ip);
  const window = rates().get(hash);
  assert.ok(window, label);
  assert.equal(JSON.stringify([...rates().keys()]).includes(ip), false, label);
  assert.equal(JSON.stringify(list()).includes(ip), false, label);
  assert.ok(window.resetAt - Date.now() <= 60 * 60 * 1000, label);
  assert.ok(window.resetAt - Date.now() > 59 * 60 * 1000, label);
  if (label === 'kv') {
    const ttl = env.SIGNUPS.puts.filter((item) => item.key === `rate:${hash}`).map((item) => item.opts?.expirationTtl);
    assert.ok(ttl.length >= 1, label);
    assert.ok(ttl.every((value) => value >= 60 && value <= 3600), label);
  }
  window.resetAt = Date.now() - 1;
  if (label === 'kv') env.SIGNUPS.rows.set(`rate:${hash}`, JSON.stringify(window));
  const afterHour = await post({ ...validBody, email: `after-hour-${label}@example.com` }, env, headers);
  assert.equal(afterHour.status, 200, label);

  const bulky = await post(
    JSON.stringify({ ...validBody, email: 'bulk@example.com', note: 'x'.repeat(9000) }),
    env,
    { 'cf-connecting-ip': '198.51.100.43' },
  );
  assert.equal(bulky.status, 413, label);
  assert.equal(list().some((record) => record.email === 'bulk@example.com'), false, label);

  const missing = await post('null', env, { 'cf-connecting-ip': '198.51.100.44' });
  assert.equal(missing.status, 400, label);
  const longName = await post(
    { ...validBody, name: 'A'.repeat(201), email: 'long@example.com' },
    env,
    { 'cf-connecting-ip': '198.51.100.45' },
  );
  assert.equal(longName.status, 400, label);

  const forwarded = await post(
    { ...validBody, email: `forward-${label}@example.com`, utm_source: 'u'.repeat(500) },
    env,
    { 'x-forwarded-for': '203.0.113.9, 10.0.0.8' },
  );
  assert.equal(forwarded.status, 200, label);
  const forwardedRow = list().find((record) => record.email === `forward-${label}@example.com`);
  assert.equal(forwardedRow.utm_source.length, 200);
  assert.equal(JSON.stringify(list()).includes('203.0.113.9'), false);
  const forwardedHash = await sha256('203.0.113.9');
  assert.ok(rates().has(forwardedHash), label);
}

function parseStamp(value) {
  const match = value.trim().match(/^(\d+):(\d+):(\d+)\.(\d+)$/);
  if (!match) throw new Error(`bad stamp ${value}`);
  const [, hours, minutes, seconds, fraction] = match;
  const millis = `${fraction}000`.slice(0, 3);
  return Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds) + Number(millis) / 1000;
}

function parseVtt(text) {
  const cues = [];
  for (const block of text.trim().split(/\n\n+/)) {
    const lines = block.split('\n');
    const timing = lines.find((line) => line.includes('-->'));
    if (!timing) continue;
    const [start, end] = timing.split('-->');
    cues.push({
      start: parseStamp(start),
      end: parseStamp(end),
      text: lines.slice(lines.indexOf(timing) + 1).join('\n'),
    });
  }
  return cues;
}

function mp4DurationSeconds(path) {
  const buffer = readFileSync(path);
  const view = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength);
  function walk(start, end) {
    let cursor = start;
    while (cursor + 8 <= end) {
      let size = view.getUint32(cursor);
      const type = String.fromCharCode(
        view.getUint8(cursor + 4),
        view.getUint8(cursor + 5),
        view.getUint8(cursor + 6),
        view.getUint8(cursor + 7),
      );
      let header = 8;
      if (size === 1) {
        size = Number(view.getBigUint64(cursor + 8));
        header = 16;
      } else if (size === 0) {
        size = end - cursor;
      }
      if (size < header) break;
      const body = cursor + header;
      const boxEnd = Math.min(cursor + size, end);
      if (type === 'mvhd') {
        const version = view.getUint8(body);
        if (version === 1) {
          return Number(view.getBigUint64(body + 24)) / view.getUint32(body + 20);
        }
        return view.getUint32(body + 16) / view.getUint32(body + 12);
      }
      if (type === 'moov' || type === 'trak' || type === 'mdia') {
        const found = walk(body, boxEnd);
        if (found) return found;
      }
      cursor += size;
    }
    return null;
  }
  const duration = walk(0, view.byteLength);
  if (!duration) throw new Error('mp4 has no duration');
  return duration;
}
