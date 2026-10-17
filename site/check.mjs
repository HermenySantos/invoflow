import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CONFIG } from './public/js/config.js';
import { copy } from './public/js/copy.js';
import { isQualified, parseAnswers, readUtm } from './public/js/qualify.js';
import { onRequestPost } from './functions/api/signup.js';
import { onRequest as onAsset } from './functions/assets/[[path]].js';
import { onRequest as onGuard } from './functions/_middleware.js';
import { captionFiles } from './tools/captions.mjs';

const root = dirname(fileURLToPath(import.meta.url));
const pub = join(root, 'public');
const read = (path) => readFileSync(join(pub, path), 'utf8');

assert.equal(existsSync(join(pub, '404.html')), true, 'public/404.html');
assert.equal(existsSync(join(pub, 'index.html')), true, 'public/index.html');
assert.equal(existsSync(join(pub, 'README.md')), false, 'README stays out of public');
assert.equal(existsSync(join(pub, 'check.mjs')), false, 'check stays out of public');
assert.equal(existsSync(join(pub, 'tools')), false, 'tools stays out of public');
assert.equal(existsSync(join(root, 'README.md')), true, 'README stays in site');
assert.equal(existsSync(join(root, 'check.mjs')), true, 'check stays in site');
assert.equal(existsSync(join(root, 'tools', 'captions.mjs')), true, 'captions stay in tools');
assert.equal(existsSync(join(root, 'tools', 'record-demo.mjs')), true, 'recorder stays in tools');
assert.equal(existsSync(join(pub, 'vercel.json')), false, 'vercel.json stays out of public');
assert.equal(existsSync(join(root, 'vercel.json')), true, 'vercel.json stays in site');
assert.equal(existsSync(join(pub, 'assets', 'demo-timeline.json')), false, 'timeline stays out of public');
assert.equal(existsSync(join(root, 'tools', 'demo-timeline.json')), true, 'timeline stays in tools');

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
assert.ok(privacy.includes('rel="canonical" href="https://invoflow.pt/privacy/"'));
assert.ok(privacy.includes('property="og:url" content="https://invoflow.pt/privacy/"'));

const sitemap = read('sitemap.xml');
assert.ok(sitemap.includes('<loc>https://invoflow.pt/</loc>'));
assert.ok(sitemap.includes('<loc>https://invoflow.pt/privacy/</loc>'));
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
const elsewhere = [read('index.html'), read('js/main.js'), read('js/copy.js'), readFileSync(join(root, 'functions/api/signup.js'), 'utf8')].join(
  '\n',
);
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

const unconfigured = await post(validBody, {});
assert.equal(unconfigured.status, 501);

const secretOnly = await post(validBody, { IP_HASH_SECRET: 'test-secret' });
assert.equal(secretOnly.status, 501);

const kvOnly = memoryKv();
const kvResponse = await post(validBody, { IP_HASH_SECRET: 'test-secret', SIGNUPS: kvOnly });
assert.equal(kvResponse.status, 501);
assert.equal(kvOnly.rows.size, 0);

const missing = await post({ email: 'ana@example.com' }, { DB: memoryDb() });
assert.equal(missing.status, 400);

const db = memoryDb();
const env = { DB: db };
const saved = await post({ ...validBody, regime: 'mensal', qualified: true, password: 'secret' }, env, {
  'cf-connecting-ip': '198.51.100.4',
});
assert.equal(saved.status, 200);
assert.equal(saved.headers.get('x-content-type-options'), 'nosniff');
assert.equal(saved.headers.get('cache-control'), 'no-store');
const savedText = await saved.text();
assert.equal(savedText, '{"ok":true}');
const stored = db.signups.map((row) => JSON.parse(row.payload));
assert.equal(stored.length, 1);
assert.equal(stored[0].qualified, false);
assert.equal(stored[0].utm_source, 'meta');
assert.equal(stored[0].email, 'ana@example.com');
assert.equal(Object.hasOwn(stored[0], 'password'), false);
assert.equal(JSON.stringify(db.rates).includes('198.51.100.4'), false);

const duplicate = await post(
  { ...validBody, name: 'Outra Pessoa', email: '  Ana@Example.com ' },
  env,
  { 'cf-connecting-ip': '198.51.100.5' },
);
assert.equal(duplicate.status, 200);
const duplicateText = await duplicate.text();
assert.equal(duplicateText, savedText);
assert.equal(db.signups.filter((row) => JSON.parse(row.payload).email === 'ana@example.com').length, 1);
assert.equal(JSON.parse(db.signups[0].payload).name, 'Ana Costa');

const dotted = await post(
  { ...validBody, email: 'User@Example.com.' },
  env,
  { 'cf-connecting-ip': '198.51.100.6' },
);
assert.equal(dotted.status, 200);
assert.equal(JSON.parse(db.signups.at(-1).payload).email, 'user@example.com');

const wideAt = await post(
  { ...validBody, email: '\uFF34este@Ex\u00E4mple.com.' },
  env,
  { 'cf-connecting-ip': '198.51.100.7' },
);
assert.equal(wideAt.status, 200);
const wideEmail = JSON.parse(db.signups.at(-1).payload).email;
assert.equal(wideEmail, `teste@${new URL('http://ex\u00E4mple.com').hostname}`);
assert.equal(wideEmail.includes('\u00E4'), false);

const beforeHoneypot = db.statements.length;
const honeypot = await post({ extra: 'https://spam.example' }, env, { 'cf-connecting-ip': '198.51.100.8' });
assert.equal(honeypot.status, 200);
assert.equal(await honeypot.text(), savedText);
assert.equal(db.signups.some((row) => JSON.parse(row.payload).email === ''), false);
const honeypotSql = db.statements.slice(beforeHoneypot);
const beforeDuplicateSql = db.statements.length;
await post({ ...validBody, email: 'ana@example.com' }, env, { 'cf-connecting-ip': '198.51.100.9' });
const duplicateSql = db.statements.slice(beforeDuplicateSql);
const beforeFresh = db.statements.length;
await post({ ...validBody, email: 'fresh-round@example.com' }, env, { 'cf-connecting-ip': '198.51.100.15' });
const freshSql = db.statements.slice(beforeFresh);
assert.deepEqual(honeypotSql, duplicateSql);
assert.deepEqual(duplicateSql, freshSql);
assert.ok(freshSql.some((sql) => sql.includes('count + 1') && sql.includes('RETURNING') && sql.includes('reset_at')));

const blankHoneypot = await post(
  { ...validBody, email: 'empty-hp@example.com', extra: '   ' },
  env,
  { 'cf-connecting-ip': '198.51.100.40' },
);
assert.equal(blankHoneypot.status, 200);
const kept = db.signups.map((row) => JSON.parse(row.payload)).find((record) => record.email === 'empty-hp@example.com');
assert.ok(kept);
assert.equal(Object.hasOwn(kept, 'extra'), false);

const quotaDb = memoryDb();
const quotaEnv = { DB: quotaDb };
const quotaIp = '198.51.100.10';
for (let index = 0; index < 5; index += 1) {
  const response = await post({ ...validBody, email: `quota-${index}@example.com` }, quotaEnv, {
    'cf-connecting-ip': quotaIp,
  });
  assert.equal(response.status, 200, `quota ${index}`);
}
const blocked = await post({ ...validBody, email: 'quota-blocked@example.com' }, quotaEnv, {
  'cf-connecting-ip': quotaIp,
});
assert.equal(blocked.status, 429);
assert.equal(blocked.headers.get('cache-control'), 'no-store');
assert.equal(blocked.headers.get('x-content-type-options'), 'nosniff');
const blockedBody = await blocked.json();
assert.equal(blockedBody.ok, false);
assert.match(blockedBody.message.pt, /hora/);
assert.match(blockedBody.message.en, /hour/);
assert.equal(quotaDb.signups.length, 5);
assert.equal([...quotaDb.rates.values()][0].count, 6);

const parallelDb = memoryDb();
const parallel = await Promise.all(
  Array.from({ length: 20 }, (_, index) =>
    post({ ...validBody, email: `parallel-${index}@example.com` }, { DB: parallelDb }, {
      'cf-connecting-ip': '198.51.100.20',
    }),
  ),
);
const parallelStatuses = await Promise.all(parallel.map(async (response) => response.status));
assert.equal(parallelStatuses.filter((status) => status === 200).length, 5);
assert.equal(parallelStatuses.filter((status) => status === 429).length, 15);
assert.equal(parallelDb.signups.length, 5);
assert.equal([...parallelDb.rates.values()][0].count, 20);

const sameEmailDb = memoryDb();
const twins = await Promise.all([
  post({ ...validBody, email: 'Twin@Example.com' }, { DB: sameEmailDb }, { 'cf-connecting-ip': '198.51.100.21' }),
  post({ ...validBody, email: 'twin@example.com.' }, { DB: sameEmailDb }, { 'cf-connecting-ip': '198.51.100.22' }),
]);
assert.deepEqual(await Promise.all(twins.map(async (response) => response.status)), [200, 200]);
assert.equal(sameEmailDb.signups.length, 1);

quotaDb.rates.set('stale-other', { count: 4, resetAt: Date.now() - 1000 });
const currentKey = [...quotaDb.rates.keys()].find((key) => key !== 'stale-other');
quotaDb.rates.get(currentKey).resetAt = Date.now() - 1000;
const afterHour = await post({ ...validBody, email: 'after-hour@example.com' }, quotaEnv, {
  'cf-connecting-ip': quotaIp,
});
assert.equal(afterHour.status, 200);
assert.equal(quotaDb.rates.has('stale-other'), false);
assert.equal(quotaDb.rates.get(currentKey).count, 1);

const v6Db = memoryDb();
for (let index = 0; index < 5; index += 1) {
  const response = await post({ ...validBody, email: `v6-${index}@example.com` }, { DB: v6Db }, {
    'cf-connecting-ip': '2001:db8:85a3::8a2e:370:7334',
  });
  assert.equal(response.status, 200, `v6 ${index}`);
}
const v6Blocked = await post({ ...validBody, email: 'v6-other@example.com' }, { DB: v6Db }, {
  'cf-connecting-ip': '2001:db8:85a3:0:ffff::1',
});
assert.equal(v6Blocked.status, 429);
assert.equal(v6Db.rates.size, 1);
const v6Other = await post({ ...validBody, email: 'v6-prefix@example.com' }, { DB: v6Db }, {
  'cf-connecting-ip': '2001:db8:85a3:1::1',
});
assert.equal(v6Other.status, 200);

const forwarded = await post(validBody, { DB: memoryDb() }, {
  'x-forwarded-for': '203.0.113.9',
  'cf-connecting-ip': '',
});
assert.equal(forwarded.status, 400);

const typed = await post(
  JSON.stringify({ ...validBody, email: 'typed@example.com' }),
  { DB: memoryDb() },
  { 'content-type': 'application/json; charset=utf-8', 'cf-connecting-ip': '198.51.100.30' },
);
assert.equal(typed.status, 200);
const plain = await post(validBody, { DB: memoryDb() }, {
  'content-type': 'text/plain',
  'cf-connecting-ip': '198.51.100.31',
});
assert.equal(plain.status, 400);

const foreign = await post(validBody, { DB: memoryDb() }, {
  origin: 'https://evil.test',
  'cf-connecting-ip': '198.51.100.32',
});
assert.equal(foreign.status, 403);
const allowed = await post(
  { ...validBody, email: 'allowed@example.com' },
  { DB: memoryDb(), SIGNUP_ORIGINS: 'https://invoflow.pt, https://preview.test' },
  { origin: 'https://preview.test', 'cf-connecting-ip': '198.51.100.33' },
);
assert.equal(allowed.status, 200);

const wide = JSON.stringify({ ...validBody, email: 'wide@example.com', note: 'é'.repeat(4000) });
assert.ok(wide.length < 8192);
assert.ok(new TextEncoder().encode(wide).byteLength > 8192);
const wideBody = await post(wide, { DB: memoryDb() }, { 'cf-connecting-ip': '198.51.100.34' });
assert.equal(wideBody.status, 413);
assert.equal(wideBody.headers.get('x-content-type-options'), 'nosniff');

const longName = await post(
  { ...validBody, name: 'A'.repeat(201), email: 'long@example.com' },
  { DB: memoryDb() },
  { 'cf-connecting-ip': '198.51.100.35' },
);
assert.equal(longName.status, 400);

const homeSource = read('index.html');
assert.match(homeSource, /class="honeypot"[\s\S]*name="extra"/);
assert.match(homeSource, /id="extra"[^>]*type="text"[^>]*autocomplete="off"/);
assert.equal(/website/i.test(homeSource), false);
assert.match(read('js/main.js'), /extra: form\.extra\.value/);
assert.match(read('js/main.js'), /response\.status === 429/);
assert.match(read('css/site.css'), /\.honeypot\s*\{/);
assert.match(read('privacy/index.html'), /O endereço IP não é guardado\./);
assert.match(read('privacy/index.html'), /O pedido seguinte apaga os resumos com mais de uma hora\./);
assert.match(read('privacy/index.html'), /The IP address is not stored\./);
assert.match(read('privacy/index.html'), /The next request deletes summaries older than one hour\./);
assert.equal(/expira ao fim de uma hora/i.test(read('privacy/index.html')), false);
assert.equal(/expires after one hour/i.test(read('privacy/index.html')), false);

const timeline = JSON.parse(readFileSync(join(root, 'tools/demo-timeline.json'), 'utf8'));
const duration = mp4DurationSeconds(join(pub, 'assets/demo-short.mp4'));
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
assert.equal(read('assets/captions-pt.vtt').includes('exemplo ilustrativo'), false);
assert.match(read('assets/captions-pt.vtt'), /Enviar ao contabilista\./);
assert.equal(read('assets/captions-pt.vtt').includes('Contabilista'), false);

assert.equal(/hreflang/i.test(homeSource), false);
assert.equal(/hreflang/i.test(read('privacy/index.html')), false);
const notFound = read('404.html');
assert.equal(/hreflang/i.test(notFound), false);
assert.match(notFound, /Página não encontrada/);
assert.match(notFound, /id="lang-toggle"/);
assert.match(notFound, /src="\/js\/not-found\.js"/);
assert.match(read('js/not-found.js'), /Page not found/);
assert.match(read('js/not-found.js'), /Este endereço não existe\./);

const headerFile = read('_headers');
assert.match(headerFile, /^ {2}Strict-Transport-Security: max-age=31536000; includeSubDomains$/m);
assert.equal(/preload/i.test(headerFile), false);

const clip = Uint8Array.from({ length: 10 }, (_, index) => index);
const assetEnv = {
  ASSETS: {
    async fetch(request) {
      const url = new URL(request.url);
      if (url.pathname.endsWith('.missing.mp4')) return new Response(null, { status: 404 });
      const type = url.pathname.endsWith('.mp4') ? 'video/mp4' : 'image/jpeg';
      return new Response(clip, { status: 200, headers: { 'content-type': type } });
    },
  },
};

const ranged = await assetCall('/assets/demo-short.mp4', { range: 'bytes=0-1' });
assert.equal(ranged.status, 206);
assert.equal(ranged.headers.get('accept-ranges'), 'bytes');
assert.equal(ranged.headers.get('content-range'), 'bytes 0-1/10');
assert.equal(ranged.headers.get('content-type'), 'video/mp4');
assert.deepEqual([...new Uint8Array(await ranged.arrayBuffer())], [0, 1]);

const whole = await assetCall('/assets/demo-short.mp4');
assert.equal(whole.status, 200);
assert.equal(whole.headers.get('accept-ranges'), 'bytes');
assert.equal(Number(whole.headers.get('content-length')), 10);
assert.equal((await whole.arrayBuffer()).byteLength, 10);

const head = await assetCall('/assets/demo-short.mp4', { method: 'HEAD' });
assert.equal(head.status, 200);
assert.equal(head.headers.get('accept-ranges'), 'bytes');
assert.equal(Number(head.headers.get('content-length')), 10);
assert.equal((await head.arrayBuffer()).byteLength, 0);

const headRange = await assetCall('/assets/demo-short.mp4', { method: 'HEAD', range: 'bytes=0-1' });
assert.equal(headRange.status, 206);
assert.equal(headRange.headers.get('content-range'), 'bytes 0-1/10');
assert.equal((await headRange.arrayBuffer()).byteLength, 0);

const invalid = await assetCall('/assets/demo-short.mp4', { range: 'bytes=20-30' });
assert.equal(invalid.status, 416);
assert.equal(invalid.headers.get('content-range'), 'bytes */10');
assert.equal(invalid.headers.get('accept-ranges'), 'bytes');

const poster = await assetCall('/assets/poster.jpg', { range: 'bytes=0-1' });
assert.equal(poster.status, 200);
assert.equal(poster.headers.get('content-type'), 'image/jpeg');

for (const path of ['/.env', '/.git/config', '/admin', '/privacy//']) {
  const response = await onGuard({
    request: new Request(`https://pilot.test${path}`),
    next() {
      return new Response('page', { status: 200 });
    },
  });
  assert.equal(response.status, 404, path);
}
const privacyPage = await onGuard({
  request: new Request('https://pilot.test/privacy/'),
  next() {
    return new Response('page', { status: 200 });
  },
});
assert.equal(privacyPage.status, 200);

console.log('site checks passed');

function assetCall(path, { method = 'GET', range } = {}) {
  const headers = new Headers();
  if (range) headers.set('range', range);
  return onAsset({
    request: new Request(`https://pilot.test${path}`, { method, headers }),
    env: assetEnv,
  });
}

function memoryKv() {
  const rows = new Map();
  return {
    rows,
    async get() {
      return null;
    },
    async put(key, value) {
      rows.set(key, value);
    },
  };
}

function memoryDb() {
  const signups = [];
  const rates = new Map();
  const statements = [];
  return {
    signups,
    rates,
    statements,
    prepare(sql) {
      const text = sql.replace(/\s+/g, ' ').trim();
      return {
        bind(...args) {
          const exec = async () => {
            await Promise.resolve();
            statements.push(text);
            if (text.startsWith('DELETE FROM signup_rates')) {
              const now = Number(args[0]);
              const keep = args[1];
              for (const [key, row] of [...rates]) {
                if (Number(row.resetAt) <= now && key !== keep) rates.delete(key);
              }
              return null;
            }
            if (text.includes('ON CONFLICT(ip_hash)')) {
              const hash = args[0];
              const windowEnd = Number(args[1]);
              const now = Number(args[2]);
              const current = rates.get(hash);
              const fresh = !current || Number(current.resetAt) <= now;
              const next = fresh
                ? { count: 1, resetAt: windowEnd }
                : { count: Number(current.count) + 1, resetAt: Number(current.resetAt) };
              rates.set(hash, next);
              return { count: next.count, reset_at: next.resetAt };
            }
            if (text.startsWith('INSERT INTO signups')) {
              const flag = Number(args[4]);
              const email = args[1];
              if (flag === 1 && email && !signups.some((row) => row.email === email)) {
                signups.push({ id: args[0], email, payload: args[2], receivedAt: args[3] });
              }
              return null;
            }
            throw new Error(`unexpected sql ${text}`);
          };
          return {
            async first() {
              return exec();
            },
            async run() {
              await exec();
              return {};
            },
          };
        },
      };
    },
  };
}

function post(body, env = {}, headers = {}) {
  const requestHeaders = {
    'content-type': 'application/json',
    origin: 'https://pilot.test',
    'cf-connecting-ip': '198.51.100.10',
    ...headers,
  };
  if (requestHeaders['content-type'] === '') delete requestHeaders['content-type'];
  if (requestHeaders['cf-connecting-ip'] === '') delete requestHeaders['cf-connecting-ip'];
  if (requestHeaders.origin === '') delete requestHeaders.origin;
  const merged = { IP_HASH_SECRET: 'test-secret', ...env };
  return onRequestPost({
    request: new Request('https://pilot.test/api/signup', {
      method: 'POST',
      headers: requestHeaders,
      body: typeof body === 'string' ? body : JSON.stringify(body),
    }),
    env: merged,
  });
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
