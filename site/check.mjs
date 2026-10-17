import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CONFIG } from './js/config.js';
import { copy } from './js/copy.js';
import { isQualified, parseAnswers, readUtm } from './js/qualify.js';
import { onRequestPost } from './functions/api/signup.js';

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

const store = new Map();
const saved = await onRequestPost({
  request: new Request('https://pilot.test/api/signup', {
    method: 'POST',
    body: JSON.stringify({ ...validBody, regime: 'mensal', qualified: true }),
  }),
  env: { SIGNUPS: { async put(key, value) { store.set(key, value); } } },
});
assert.equal(saved.status, 200);
const stored = JSON.parse([...store.values()][0]);
assert.equal(stored.qualified, false);
assert.equal(stored.utm_source, 'meta');
assert.equal(Object.hasOwn(stored, 'password'), false);

console.log('site checks passed');
