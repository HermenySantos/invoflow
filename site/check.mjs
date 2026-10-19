import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CONFIG } from './public/js/config.js';
import { copy } from './public/js/copy.js';
import { readUtm } from './public/js/qualify.js';
import { CONSENT_TEXT_VERSION, onRequestPost } from './functions/api/signup.js';
import { onRequest as onAsset } from './functions/assets/[[path]].js';
import { onRequest as onGuard } from './functions/_middleware.js';
import { SECURITY_HEADERS } from './functions/security.js';
import { captionFiles } from './tools/captions.mjs';
import { missingCopy } from './tools/copycheck.mjs';

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
const visible = pages.join('\n').replaceAll('[prazo]', '');

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

const home = read('index.html');
for (const key of ['heroTitle', 'heroSub', 'cta', 'caveat', 'friction', 'consentBody', 'thanksTitle', 'thanksBody']) {
  assert.ok(home.includes(copy.pt[key]), key);
}
assert.deepEqual(missingCopy(), { pt: [], en: [] });
assert.equal(copy.pt.colBase, 'Líquido (EUR)');
assert.equal(copy.en.colBase, 'Net (EUR)');
assert.equal(home.includes('priceLine'), false);
assert.equal(home.includes('pilotPrice'), false);
const moneySources = [
  home,
  read('privacy/index.html'),
  read('404.html'),
  read('js/copy.js'),
  read('js/main.js'),
  read('assets/captions-pt.vtt'),
  read('assets/captions-en.vtt'),
].join('\n');
assert.equal(findUnlabelledMoney(moneySources), null, 'money outside an example or estimate label');
assert.equal(findUnlabelledMoney(metaAndOg(home + read('privacy/index.html') + read('404.html'))), null, 'money in meta or og');
assert.equal(/\b\d[\d.,]*\s*(?:\/\s*trimestre|por\s+trimestre|per\s+quarter)\b/i.test(stripLabelled(moneySources)), false);
assert.equal(stripLabelled(moneySources).includes('Pack IVA'), false);
assert.match(home, /data-label="example"[\s\S]*Exemplo, Lda[\s\S]*23,00[\s\S]*41,86[\s\S]*230,00/);
assert.match(home, /data-label="estimate"[\s\S]*188,14/);
for (const sample of [
  '€19',
  '19 €',
  '19€',
  '€ 19',
  '19 EUR',
  'EUR 19',
  '19EUR',
  'EUR19',
  '19 euro',
  '19 euros',
  'euro 19',
  'euros 19',
  '19,00 EUR',
  'EUR 23.00',
  '1.190 euros',
  '€23,00',
]) {
  assert.notEqual(findUnlabelledMoney(`<p>${sample}</p>`), null, `unlabelled ${sample}`);
  assert.equal(findUnlabelledMoney(`<p data-label="example">${sample}</p>`), null, `example ${sample}`);
  assert.equal(findUnlabelledMoney(`<section data-label="estimate">${sample}</section>`), null, `estimate ${sample}`);
  assert.notEqual(findUnlabelledMoney(`<meta property="og:description" content="${sample}">`), null, `og ${sample}`);
  assert.notEqual(findUnlabelledMoney(`<meta name="description" content="${sample}">`), null, `meta ${sample}`);
}
for (const sample of ['23%', '23 %', '100%', 'IVA 23%', 'about 23% of invoices', 'Base (EUR)', 'Líquido (EUR)', 'IVA (EUR)', 'Net (EUR)', 'VAT (EUR)']) {
  assert.equal(findUnlabelledMoney(`<p>${sample}</p>`), null, `not money ${sample}`);
  assert.equal(findUnlabelledMoney(`<meta name="description" content="${sample}">`), null, `meta not money ${sample}`);
}
const bareCue = 'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n19 euros\n';
assert.notEqual(findUnlabelledMoney(bareCue), null, 'unlabelled caption');
assert.equal(findUnlabelledMoney('WEBVTT\n\nexample\n00:00:00.000 --> 00:00:01.000\n19 euros\n'), null, 'example caption');
assert.equal(findUnlabelledMoney('WEBVTT\n\nestimate\n00:00:00.000 --> 00:00:01.000\n€23.00\n'), null, 'estimate caption');
assert.notEqual(
  findUnlabelledMoney('WEBVTT\n\nexample\n00:00:00.000 --> 00:00:01.000\n€1\n\n00:00:01.000 --> 00:00:02.000\n19 EUR\n'),
  null,
  'cue after a label',
);
assert.match(home, /<a class="btn btn--outline btn--sm" href="#lista" data-cta/);
assert.equal(home.includes('btn btn--primary btn--sm'), false);
assert.match(home, /<div class="hero__cta">[\s\S]*?<a class="btn btn--primary btn--lg" href="#lista" data-cta/);
assert.match(home, /<p class="kicker" aria-hidden="true">02<\/p>/);
assert.match(home, /<p class="kicker" aria-hidden="true">03<\/p>/);
assert.match(home, /<p class="kicker" aria-hidden="true">04<\/p>/);
assert.match(home, /<p class="kicker kicker--on-deep" aria-hidden="true">05<\/p>/);
assert.match(home, /<p class="kicker" aria-hidden="true">06<\/p>/);
assert.match(home, /<p class="kicker" aria-hidden="true">07<\/p>/);
assert.equal(/<p class="kicker[^"]*" aria-hidden="true">01<\/p>/.test(home), false);
assert.match(home, /<ol class="terms">/);
for (const numeral of ['i', 'ii', 'iii', 'iv', 'v', 'vi']) {
  assert.match(home, new RegExp(`<span class="term__no" aria-hidden="true">${numeral}</span>`));
}
assert.match(home, /<h2 id="form-title" class="h2 h2--xxl"/);
assert.match(read('js/main.js'), /addEventListener\('input'/);
assert.equal((home.match(/href="\/privacy\/"/g) || []).length, 3);
assert.equal(/href="\/privacy"(?!\/)/.test(home), false);
assert.equal(/https:\/\/invoflow\.pt\/privacy(?!\/)/.test(home), false);
assert.ok(home.includes('rel="canonical" href="https://invoflow.pt/"'));
assert.ok(home.includes('property="og:url" content="https://invoflow.pt/"'));
assert.ok(home.includes('pack para enviar ao seu contabilista'));
assert.ok(home.includes('Exemplo ilustrativo com dados fictícios.'));
assert.ok(home.includes('Estimativa do IVA a entregar'));
assert.ok(home.includes('Exemplo · dados fictícios'));
assert.equal((home.match(/exemplo ilustrativo/g) || []).length, 0);
assert.equal(/<details\b[^>]*\bopen\b/.test(home), false);

const privacy = read('privacy/index.html');
assert.ok(privacy.includes('href="/"'));
assert.equal(privacy.includes('Hermenegildo Jerónimo dos Santos'), false);
assert.equal(privacy.includes('hermeny7@hotmail.com'), false);
assert.equal(privacy.includes('mailto:contact@invoflow.pt'), false);
assert.ok(privacy.includes('mailto:contacto@invoflow.pt'));
assert.equal(privacy.includes('Este valor ignora o IVA das vendas.'), false);
assert.equal(privacy.includes('É uma estimativa, não um cálculo oficial.'), false);
assert.ok(privacy.includes('Lista de interesse'));
assert.ok(privacy.includes('O email que indicar, a data e a confirmação do seu consentimento'));
assert.ok(privacy.includes('ou escrevendo para'));
assert.ok(privacy.includes('Depois disso, deixamos de lhe escrever.'));
assert.ok(privacy.includes('<span class="token">[alojamento e retenção da lista: onde fica guardada, durante quanto tempo, o que acontece quando sai — aguarda decisão do Gildo]</span>'));
assert.ok(privacy.includes('<span class="token">[entidade e NIF]</span>'));
assert.ok(privacy.includes('<span class="token">[texto sobre o endereço IP — aguarda correção técnica:'));
assert.ok(privacy.includes('Interest list'));
assert.ok(privacy.includes('or write to'));
assert.ok(privacy.includes('After that, we stop writing to you.'));
assert.ok(privacy.includes("<span class=\"token\">[interest-list hosting and retention: where it's stored, for how long, what happens when you leave — awaiting Gildo's decision]</span>"));
assert.ok(privacy.includes('<span class="token">[entity and tax number]</span>'));
assert.ok(privacy.includes('<span class="token">[IP address wording — awaiting a technical fix:'));
assert.equal(privacy.includes('<span class="token">[prazo]</span>'), false);
assert.ok(privacy.includes('rel="canonical" href="https://invoflow.pt/privacy/"'));
assert.ok(privacy.includes('property="og:url" content="https://invoflow.pt/privacy/"'));
assert.equal(/href="\/privacy"(?!\/)/.test(privacy), false);
assert.equal(/https:\/\/invoflow\.pt\/privacy(?!\/)/.test(privacy), false);

const sitemap = read('sitemap.xml');
assert.ok(sitemap.includes('<loc>https://invoflow.pt/</loc>'));
assert.ok(sitemap.includes('<loc>https://invoflow.pt/privacy/</loc>'));
assert.equal(/https:\/\/invoflow\.pt\/privacy(?!\/)/.test(sitemap), false);
assert.equal(/hreflang/i.test(sitemap), false);
const redirects = read('_redirects').trim();
assert.equal(redirects, '/privacy /privacy/ 308');
const vercel = JSON.parse(readFileSync(join(root, 'vercel.json'), 'utf8'));
assert.equal(vercel.cleanUrls, true);
assert.equal(vercel.trailingSlash, true);
assert.equal(Object.hasOwn(vercel, 'redirects'), false);
assert.ok(read('robots.txt').includes('Sitemap: https://invoflow.pt/sitemap.xml'));

assert.equal(CONFIG.FORM_ENDPOINT, '');
assert.equal(CONFIG.DEPOSIT_ENABLED, false);
assert.equal(CONFIG.STRIPE_PAYMENT_LINK, '');
assert.equal(CONFIG.ANALYTICS, '');
assert.equal(CONFIG.META_PIXEL_ID, '');

const params = new URLSearchParams('utm_source=meta&utm_medium=cpc&utm_campaign=pilot&utm_term=ignore');
assert.deepEqual(readUtm(params), {
  utm_source: 'meta',
  utm_medium: 'cpc',
  utm_campaign: 'pilot',
});

const interestFiles = [read('index.html'), read('js/main.js'), read('js/copy.js'), read('js/qualify.js'), readFileSync(join(root, 'functions/api/signup.js'), 'utf8')].join(
  '\n',
);
assert.equal(interestFiles.includes("regime === 'trimestral'"), false);
assert.equal(interestFiles.includes('name="regime"'), false);
assert.equal(interestFiles.includes('name="volume"'), false);
assert.equal(interestFiles.includes('name="accountant"'), false);
assert.equal(interestFiles.includes('qualified'), false);
assert.equal(interestFiles.includes('parseAnswers'), false);
assert.equal(interestFiles.includes('isQualified'), false);

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
assert.equal(home.includes('id="piloto"'), false);
assert.ok(home.includes('id="limites"'));
assert.ok(home.includes('id="lista"'));
assert.ok(home.includes('data-i18n="termGetTitle"'));
assert.ok(visitor.includes('What you get'));
assert.ok(visitor.includes('O que recebe'));
assert.equal(visitor.includes('Pack IVA'), false);
assert.ok(home.includes('mailto:contacto@invoflow.pt'));
assert.equal(home.includes('mailto:contact@invoflow.pt'), false);
assert.equal(visitor.includes('Reservar lugar no piloto'), false);
assert.ok(visitor.includes('Avisem-me'));
assert.ok(visitor.includes('Keep me posted'));
assert.equal(visitor.includes('Notify me'), false);
assert.ok(visitor.includes('Aceito receber emails da Invoflow sobre o produto e o seu lançamento. Posso sair da lista a qualquer momento.'));
assert.ok(visitor.includes('I agree to receive emails from Invoflow about the product and its launch. I can leave the list at any time.'));
assert.ok(visitor.includes('Obrigado. Está na lista.'));
assert.ok(visitor.includes("Thanks. You're on the list."));
assert.equal(visitor.includes('Obrigado, recebemos o seu pedido. Entraremos em contacto por email.'), false);
assert.equal(visitor.includes("Thank you, we've received your request. We'll get in touch by email."), false);
assert.equal(visitor.includes('Obrigado! Vamos enviar-lhe novidades sobre o piloto.'), false);
assert.ok(visitor.includes('Só pedimos o email. Sem compromisso.'));
assert.ok(visitor.includes('Just your email. No commitment.'));
assert.ok(visitor.includes('É uma estimativa. Não substitui o contabilista.'));
assert.ok(visitor.includes("It's an estimate. It doesn't replace your accountant."));
assert.ok(visitor.includes('Limites, com honestidade'));
assert.ok(visitor.includes('Honest limits'));
assert.ok(visitor.includes('O original segue no pack para o contabilista.'));
assert.ok(visitor.includes("The original goes in your accountant's pack."));
assert.ok(visitor.includes('Fotografou, está no pack.'));
assert.ok(visitor.includes("Snap it, and it's in the pack."));
assert.ok(visitor.includes('Quer saber quando a Invoflow abrir?'));
assert.ok(visitor.includes('Want to know when Invoflow opens?'));
assert.ok(visitor.includes('Ainda não há preço público.'));
assert.ok(visitor.includes("There's no public price yet."));
assert.ok(visitor.includes('Quanto vai custar?'));
assert.ok(visitor.includes('How much will it cost?'));
assert.ok(visitor.includes('Example · fictional data'));
assert.equal(visitor.includes('IVA dedutível'), false);
assert.equal(visitor.includes('fica guardado'), false);
assert.equal(visitor.includes('ficou guardado'), false);
assert.equal(visitor.includes('The original is kept'), false);
assert.equal(visitor.includes('Photographed means kept'), false);
assert.equal(visitor.includes('[figuras do exemplo'), false);
for (const gone of [
  '[desconto',
  '[discount',
  '[trimestre do piloto',
  '[pilot quarter',
  '[canal de suporte',
  '[support channel',
  '[formato do feedback',
  '[feedback format',
  '[dias até à resposta]',
  '[days to reply]',
  'Feito na Covilhã',
  'Made in Covilhã',
  '[nome do fundador]',
  '[foto]',
  'tokMadeIn',
  'data-gated="founder"',
  'primeiro trimestre com desconto',
  'first quarter discounted',
  'first quarter is discounted',
]) {
  assert.equal(visitor.includes(gone), false, gone);
}
assert.ok(visitor.includes('Inscrições abrem em breve.'));
assert.ok(visitor.includes('Registration opens soon.'));
assert.equal(visitor.includes('Sign-ups open soon.'), false);
assert.match(home, /id="submit-pilot"[^>]*disabled/);
assert.match(home, /id="formset"[^>]*disabled/);

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
  email: 'ana@example.com',
  consent: true,
  lang: 'pt',
  utm_source: 'meta',
  utm_medium: 'cpc',
  utm_campaign: 'pilot',
};

const unconfigured = await post(validBody, {});
assert.equal(unconfigured.status, 501);
assertSecurity(unconfigured, 'signup 501');

const offOrigin = await post(validBody, { IP_HASH_SECRET: '' }, { origin: 'https://evil.test' });
assert.equal(offOrigin.status, 403);
assertSecurity(offOrigin, 'signup off origin');
const offType = await post(validBody, { IP_HASH_SECRET: '' }, { 'content-type': 'text/plain' });
assert.equal(offType.status, 400);
assertSecurity(offType, 'signup off type');

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
const saved = await post(
  {
    ...validBody,
    regime: 'mensal',
    qualified: true,
    password: 'secret',
    name: 'Ana Costa',
    consent_at: '1999-01-01T00:00:00.000Z',
    consent_text_version: 'client-spoof',
  },
  env,
  { 'cf-connecting-ip': '198.51.100.4' },
);
assert.equal(saved.status, 200);
assert.equal(saved.headers.get('x-content-type-options'), 'nosniff');
assert.equal(saved.headers.get('cache-control'), 'no-store');
assertSecurity(saved, 'signup 200');
const savedText = await saved.text();
assert.equal(savedText, '{"ok":true}');
const stored = db.signups.map((row) => JSON.parse(row.payload));
assert.equal(stored.length, 1);
assert.deepEqual(Object.keys(stored[0]).sort(), ['consent_at', 'consent_text_version', 'email', 'lang', 'utm_campaign', 'utm_medium', 'utm_source']);
assert.equal(stored[0].consent_text_version, CONSENT_TEXT_VERSION);
assert.equal(stored[0].utm_source, 'meta');
assert.equal(stored[0].email, 'ana@example.com');
assert.equal(stored[0].lang, 'pt');
assert.match(stored[0].consent_at, /^\d{4}-\d{2}-\d{2}T/);
assert.notEqual(stored[0].consent_at, '1999-01-01T00:00:00.000Z');
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
assert.equal(Object.hasOwn(JSON.parse(db.signups[0].payload), 'name'), false);

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

const signupSource = readFileSync(join(root, 'functions/api/signup.js'), 'utf8');
assert.match(signupSource, /const honeypot = text\(raw\.extra\) !== ''/);
assert.equal(/raw\.website/.test(signupSource), false);
const decoy = await post(
  { ...validBody, email: 'decoy-field@example.com', website: 'https://spam.example' },
  env,
  { 'cf-connecting-ip': '198.51.100.77' },
);
assert.equal(decoy.status, 200);
const decoyRow = db.signups.map((row) => JSON.parse(row.payload)).find((record) => record.email === 'decoy-field@example.com');
assert.ok(decoyRow);
assert.equal(Object.hasOwn(decoyRow, 'website'), false);
assert.equal(Object.hasOwn(decoyRow, 'extra'), false);
const websiteOnly = await post({ website: 'https://spam.example' }, env, { 'cf-connecting-ip': '198.51.100.78' });
assert.equal(websiteOnly.status, 400);

const rowsBeforeTrap = db.signups.length;
const trapped = await post(
  { ...validBody, email: 'bot@example.com', extra: 'https://spam.example' },
  env,
  { 'cf-connecting-ip': '198.51.100.79' },
);
assert.equal(trapped.status, 200);
assert.equal(await trapped.text(), savedText);
assert.equal(db.signups.length, rowsBeforeTrap);
assert.equal(db.signups.some((row) => row.email === 'bot@example.com'), false);

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
assertSecurity(foreign, 'signup 403');
const allowed = await post(
  { ...validBody, email: 'allowed@example.com' },
  { DB: memoryDb(), SIGNUP_ORIGINS: 'https://invoflow.pt, https://preview.test' },
  { origin: 'https://preview.test', 'cf-connecting-ip': '198.51.100.33' },
);
assert.equal(allowed.status, 200);

const wide = JSON.stringify({ ...validBody, email: 'wide@example.com', note: 'é'.repeat(4100) });
assert.ok(wide.length < 8192);
assert.ok(new TextEncoder().encode(wide).byteLength > 8192);
const wideBody = await post(wide, { DB: memoryDb() }, { 'cf-connecting-ip': '198.51.100.34' });
assert.equal(wideBody.status, 413);
assert.equal(wideBody.headers.get('x-content-type-options'), 'nosniff');
assertSecurity(wideBody, 'signup 413');

const longNameDb = memoryDb();
const longName = await post(
  { ...validBody, name: 'A'.repeat(201), email: 'long@example.com' },
  { DB: longNameDb },
  { 'cf-connecting-ip': '198.51.100.35' },
);
assert.equal(longName.status, 200);
const longRow = JSON.parse(longNameDb.signups[0].payload);
assert.equal(longRow.email, 'long@example.com');
assert.equal(Object.hasOwn(longRow, 'name'), false);
const badEmail = await post(
  { ...validBody, email: 'not-an-email' },
  { DB: memoryDb() },
  { 'cf-connecting-ip': '198.51.100.36' },
);
assert.equal(badEmail.status, 400);

const homeSource = read('index.html');
assert.match(homeSource, /class="honeypot"[\s\S]*name="extra"/);
assert.match(homeSource, /id="extra"[^>]*type="text"[^>]*autocomplete="off"/);
assert.equal(/website/i.test(homeSource), false);
assert.match(read('js/main.js'), /extra: form\.extra\.value/);
assert.match(read('js/main.js'), /response\.status === 429/);
assert.match(read('css/site.css'), /\.honeypot\s*\{/);
assert.match(read('privacy/index.html'), /escrevendo para/);
assert.match(read('privacy/index.html'), /write to/);
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
assert.equal(/s-maxage/i.test(headerFile), false);
const headerBlocks = headerSections(headerFile);
assert.deepEqual(headerBlocks.get('/*'), SECURITY_HEADERS);
assert.equal(headerBlocks.get('/404.html')?.['cache-control'], 'no-store');
assert.equal(headerBlocks.get('/fonts/*.woff2')?.['cache-control'], 'public, max-age=31536000, immutable');

const fontMarkup = [homeSource, read('privacy/index.html'), notFound, read('css/site.css')].join('\n');
assert.equal(/fonts\.(googleapis|gstatic)\.com|use\.typekit\.net/i.test(fontMarkup), false);
assert.equal(/@import\b/i.test(read('css/site.css')), false);
assert.equal(/url\(\s*['"]?https?:/i.test(fontMarkup), false);
const preloads = [];
for (const html of [homeSource, read('privacy/index.html'), notFound]) {
  for (const tag of html.matchAll(/<link\b[^>]*>/gi)) {
    if (!/\brel="[^"]*\bpreload\b/i.test(tag[0])) continue;
    const href = tag[0].match(/\bhref="([^"]+)"/);
    assert.ok(href, tag[0]);
    assert.equal(href[1].startsWith('/'), true, href[1]);
    assert.equal(existsSync(join(pub, href[1].slice(1))), true, href[1]);
    preloads.push(href[1]);
  }
}
assert.ok(preloads.includes('/fonts/fraunces-display-latin.woff2'));
assert.ok(preloads.includes('/fonts/inter-var-latin.woff2'));
for (const match of read('css/site.css').matchAll(/url\("(\/fonts\/[^"]+)"\)/g)) {
  assert.equal(existsSync(join(pub, match[1].slice(1))), true, match[1]);
}
const fontFiles = readdirSync(join(pub, 'fonts')).filter((name) => name.endsWith('.woff2'));
const licences = readdirSync(join(pub, 'fonts')).filter((name) => /ofl/i.test(name) && name.endsWith('.txt'));
assert.ok(fontFiles.length > 0);
for (const file of fontFiles) {
  const family = file.split('-')[0];
  const licence = licences.find((name) => name.toLowerCase().includes(family));
  assert.ok(licence, file);
  assert.match(readFileSync(join(pub, 'fonts', licence), 'utf8'), /SIL Open Font License/);
}

const routes = JSON.parse(read('_routes.json'));
assert.deepEqual(routes.include, ['/*']);
for (const path of ['//', '/privacy//', '/css//site.css', '/js//main.js', '/fonts//inter-var-latin.woff2', '/assets//poster-review.webp']) {
  assert.equal(routes.exclude.some((rule) => routeRuleMatches(path, rule)), false, path);
  const collapsed = path.replace(/\/{2,}/g, '/');
  assert.equal(routes.exclude.some((rule) => routeRuleMatches(collapsed, rule)), false, collapsed);
}

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
assertSecurity(ranged, 'range 206');
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
assertSecurity(invalid, 'range 416');

const poster = await assetCall('/assets/poster.jpg', { range: 'bytes=0-1' });
assert.equal(poster.status, 200);
assert.equal(poster.headers.get('content-type'), 'image/jpeg');

const sharedHeaders = { 'content-type': 'image/jpeg', 'cache-control': 'public, max-age=60, s-maxage=86400' };
const sharedEnv = {
  ASSETS: {
    async fetch(request) {
      const url = new URL(request.url);
      if (url.pathname.endsWith('.missing.mp4')) {
        return new Response('missing', { status: 404, headers: sharedHeaders });
      }
      return new Response(clip, { status: 200, headers: sharedHeaders });
    },
  },
};
for (const [path, status] of [
  ['/assets/poster.jpg', 200],
  ['/assets/demo-short.mp4', 200],
  ['/assets/gone.missing.mp4', 404],
]) {
  const response = await onAsset({
    request: new Request(`https://pilot.test${path}`),
    env: sharedEnv,
  });
  assert.equal(response.status, status, path);
  assert.equal(/s-maxage/i.test(response.headers.get('cache-control') ?? ''), false, path);
  if (status === 200 && path.endsWith('.jpg')) assert.equal(response.headers.get('cache-control'), 'public, max-age=60');
}

for (const path of ['/.env', '/.git/config', '/admin', '//', '/privacy//', '/css//site.css', '/js//main.js', '/_routes.json']) {
  const response = await onGuard({
    request: new Request(`https://pilot.test${path}`),
    next() {
      return new Response('page', { status: 200 });
    },
  });
  assert.equal(response.status, 404, path);
  assert.equal(await response.text(), 'Not found\n', path);
  assertSecurity(response, path);
  assert.equal(/s-maxage/i.test(response.headers.get('cache-control') ?? ''), false, path);
}
const sharedMiss = await onGuard({
  request: new Request('https://pilot.test/no-such'),
  next() {
    return new Response('missing', {
      status: 404,
      headers: { 'cache-control': 'public, max-age=60, s-maxage=86400', 'content-type': 'text/html' },
    });
  },
});
assert.equal(sharedMiss.status, 404);
assert.equal(sharedMiss.headers.get('cache-control'), 'public, max-age=60');
const sharedAsset = await onGuard({
  request: new Request('https://pilot.test/assets/poster.jpg'),
  next() {
    return new Response('img', {
      status: 200,
      headers: { 'cache-control': 'public, max-age=30, s-maxage=120', 'content-type': 'image/jpeg' },
    });
  },
});
assert.equal(sharedAsset.status, 200);
assert.equal(sharedAsset.headers.get('cache-control'), 'public, max-age=30');
const sharedHome = await onGuard({
  request: new Request('https://pilot.test/'),
  async next() {
    return new Response('home', {
      status: 200,
      headers: { 'cache-control': 'public, max-age=0, s-maxage=60' },
    });
  },
});
assert.equal(sharedHome.headers.get('cache-control'), 'public, max-age=0, s-maxage=60');
const privacyPage = await onGuard({
  request: new Request('https://pilot.test/privacy/'),
  next() {
    return new Response('page', { status: 200 });
  },
});
assert.equal(privacyPage.status, 200);
const privacyRedirect = await onGuard({
  request: new Request('https://pilot.test/privacy'),
  next() {
    return new Response('should-not-run', { status: 200 });
  },
});
assert.equal(privacyRedirect.status, 308);
assert.equal(privacyRedirect.headers.get('location'), '/privacy/');
assert.equal(await privacyRedirect.text(), '');
assertSecurity(privacyRedirect, 'privacy 308');
const privacyExtra = await onGuard({
  request: new Request('https://pilot.test/privacy/extra'),
  next() {
    return new Response('page', { status: 200 });
  },
});
assert.equal(privacyExtra.status, 200);

const notFoundBody = '<!doctype html><h1>Página não encontrada</h1>';
for (const path of ['/404', '/404.html']) {
  const response = await onGuard({
    request: new Request(`https://pilot.test${path}`),
    env: {
      ASSETS: {
        fetch(request) {
          assert.equal(new URL(request.url).pathname, '/404.html', path);
          return Promise.resolve(new Response(notFoundBody, {
            status: 200,
            headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'public, max-age=0, must-revalidate' },
          }));
        },
      },
    },
    next() {
      throw new Error(`next ran for ${path}`);
    },
  });
  assert.equal(response.status, 404, path);
  assert.equal(response.headers.get('cache-control'), 'no-store', path);
  assert.equal(await response.text(), notFoundBody, path);
  assertSecurity(response, path);
}
const notFoundHead = await onGuard({
  request: new Request('https://pilot.test/404', { method: 'HEAD' }),
  env: {
    ASSETS: {
      fetch() {
        return Promise.resolve(new Response(notFoundBody, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } }));
      },
    },
  },
  next() {
    throw new Error('next ran for HEAD /404');
  },
});
assert.equal(notFoundHead.status, 404);
assert.equal(notFoundHead.headers.get('cache-control'), 'no-store');
assert.equal(await notFoundHead.text(), '');

if (process.argv.includes('--release')) {
  for (const file of ['index.html', 'js/copy.js', 'privacy/index.html']) {
    const source = read(file);
    assert.equal((source.match(/class="token/g) || []).length, 0, `${file} still has .token`);
    assert.equal(/\[[^\]\r\n]+\]/.test(source), false, `${file} still has a [token]`);
  }
}

console.log('site checks passed');

function stripLabelled(html) {
  let next = String(html).replace(
    /(?:^|\n)[ \t]*(?:example|estimate)[ \t]*\n[ \t]*\d{2}:\d{2}:\d{2}\.\d{3}[ \t]*-->[^\n]*\n(?:[^\n]*\n)*?(?=\n|\s*$)/gi,
    '\n',
  );
  let previous;
  const pattern = /<([a-zA-Z0-9]+)(\s[^>]*?\bdata-label="(?:example|estimate)"[^>]*)>[\s\S]*?<\/\1>/g;
  do {
    previous = next;
    next = previous.replace(pattern, '');
  } while (next !== previous);
  return next;
}

function findUnlabelledMoney(source) {
  const outside = stripLabelled(source);
  const pattern =
    /€|\d[\d.,]*[ \t]{0,3}(?:eur|euros?)\b|\b(?:eur|euros?)[ \t]{0,3}\d/gi;
  const match = pattern.exec(outside);
  return match ? match[0] : null;
}

function metaAndOg(html) {
  const parts = [];
  for (const tag of html.matchAll(/<meta\b[^>]*>/gi)) {
    const source = tag[0];
    if (!/\b(?:name|property)="(?:description|og:[^"]+)"/i.test(source)) continue;
    const content = source.match(/\bcontent="([^"]*)"/i);
    if (content) parts.push(content[1]);
  }
  for (const title of html.matchAll(/<title>([^<]*)<\/title>/gi)) parts.push(title[1]);
  return parts.join('\n');
}

function headerSections(source) {
  const blocks = new Map();
  let section = '';
  for (const line of source.split('\n')) {
    if (line && !line.startsWith(' ') && !line.startsWith('#')) {
      section = line.trim();
      blocks.set(section, {});
      continue;
    }
    const match = line.match(/^ {2}([^:]+):\s*(.+)$/);
    if (match && section) blocks.get(section)[match[1].toLowerCase()] = match[2].trim();
  }
  return blocks;
}

function assertSecurity(response, label) {
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) {
    assert.equal(response.headers.get(name), value, `${label} ${name}`);
  }
}

function routeRuleMatches(pathname, rule) {
  let transformed;
  if (rule === '/' || rule === '/*') transformed = rule;
  else if (rule.endsWith('/*')) transformed = `${rule.slice(0, -2)}(/*)?`;
  else if (rule.endsWith('/')) transformed = `${rule.slice(0, -1)}(/)?`;
  else if (rule.endsWith('*')) transformed = rule;
  else transformed = `${rule}(/)?`;
  const source = `^${transformed.replaceAll('.', '\\.').replaceAll('*', '.*')}$`;
  return new RegExp(source).test(pathname);
}

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
