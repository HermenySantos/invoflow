import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { captionFiles, q1Deadline, q4Deadline, videoTimeline } from './captions.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const site = dirname(here);
const app = process.env.DEMO_APP_URL || 'http://127.0.0.1:3000';
const font = process.env.DEMO_FONT || '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf';
const bold = process.env.DEMO_FONT_BOLD || '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf';

const receipt = {
  vendor_name: 'Exemplo, Lda',
  vendor_nif: '999999990',
  invoice_number: 'FT 2026/1',
  document_date: '2026-03-12',
  net_amount: '100.00',
  vat_amount: '23.00',
  gross_amount: '123.00',
  vat_rate: '23.00',
  expense_category: 'office',
  status: 'ready',
};

function drawText(fontfile, text, size, color, y) {
  const escaped = text.replace(/\\/g, '\\\\').replace(/:/g, '\\:').replace(/,/g, '\\,');
  return `drawtext=fontfile=${fontfile}:text='${escaped}':fontsize=${size}:fontcolor=${color}:x=48:y=${y}`;
}

function writeInvoice(path) {
  const filter = [
    drawText(font, 'exemplo ilustrativo', 28, '0x92400E', 48),
    drawText(bold, 'Exemplo, Lda', 42, 'black', 120),
    drawText(font, 'NIF 999 999 990', 28, 'black', 190),
    drawText(font, '12 de março de 2026', 28, 'black', 250),
    drawText(font, 'Base 100,00 €', 28, 'black', 360),
    drawText(bold, 'IVA estimativa 23,00 €', 32, 'black', 420),
    drawText(bold, 'Total 123,00 €', 36, 'black', 490),
  ].join(',');
  const result = spawnSync(
    'ffmpeg',
    ['-y', '-f', 'lavfi', '-i', 'color=c=white:s=800x1000', '-vf', filter, '-frames:v', '1', path],
    { encoding: 'utf8' },
  );
  if (result.status !== 0) throw new Error(result.stderr || 'invoice image failed');
}

function paint(doc) {
  if (!doc || typeof doc !== 'object' || !('vendor_name' in doc)) return doc;
  return { ...doc, ...receipt, fictional: true };
}

async function callApi(page, path, options = {}) {
  return page.evaluate(async ({ path, options }) => {
    const user = JSON.parse(localStorage.getItem('invoflow_mock_auth'));
    const response = await fetch(path, {
      method: options.method || 'GET',
      headers: {
        'content-type': 'application/json',
        'X-Mock-User-Id': user.id,
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    const text = await response.text();
    return { status: response.status, body: text ? JSON.parse(text) : null };
  }, { path, options });
}

async function visibleLines(page) {
  return page.evaluate(() => {
    const lines = [];
    for (const node of document.querySelectorAll('body *')) {
      const text = (node.tagName === 'BUTTON' ? node.innerText : node.textContent || '')
        .replace(/\s+/g, ' ')
        .trim();
      if (node.children.length > 0 && node.tagName !== 'BUTTON') continue;
      if (!text) continue;
      const rect = node.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) continue;
      if (rect.bottom < 0 || rect.top > window.innerHeight) continue;
      lines.push(text);
    }
    return lines;
  });
}

async function showEstimate(page) {
  const fit = await page.evaluate(() => {
    const sentence = [...document.querySelectorAll('p')].find((node) =>
      (node.textContent || '').includes('Este valor ignora'),
    );
    const deadline = [...document.querySelectorAll('p')].find((node) =>
      (node.textContent || '').includes('Prazo de entrega'),
    );
    if (!sentence || !deadline) return { ok: false };
    const top = sentence.getBoundingClientRect().top + window.scrollY;
    window.scrollTo(0, Math.max(0, top - 70));
    const sentenceRect = sentence.getBoundingClientRect();
    const deadlineRect = deadline.getBoundingClientRect();
    return {
      ok: sentenceRect.top >= 0 && deadlineRect.bottom <= window.innerHeight,
      sentenceTop: sentenceRect.top,
      deadlineBottom: deadlineRect.bottom,
    };
  });
  if (!fit.ok) throw new Error(`estimate and deadline do not share the frame ${JSON.stringify(fit)}`);
}

function readPicture(path) {
  const result = spawnSync('tesseract', [path, 'stdout', '-l', 'por'], { encoding: 'utf8' });
  return result.stdout || '';
}

function assertClean(label, lines) {
  const text = lines.join('\n');
  const banned = [/continente/i, /prazo de pagamento/i, /pare de descobrir/i, /demonstração, sem cartão/i, /caf[eé]/i, /restaurante/i];
  for (const pattern of banned) {
    if (pattern.test(text)) throw new Error(`${label} shows ${pattern}`);
  }
  return text;
}

async function main() {
  const work = join(here, '.work');
  mkdirSync(work, { recursive: true });
  const invoice = join(work, 'fatura.png');
  writeInvoice(invoice);

  const browser = await chromium.launch({ headless: true });
  const setup = await browser.newContext({
    viewport: { width: 960, height: 600 },
    locale: 'pt-PT',
    timezoneId: 'Europe/Lisbon',
  });
  const signIn = await setup.newPage();
  await signIn.goto(`${app}/sign-in?next=/upload`);
  await signIn.locator('#email').fill('demo@invoflow.test');
  await signIn.locator('button[type="submit"]').click();
  await signIn.waitForURL('**/upload');
  const state = join(work, 'state.json');
  await setup.storageState({ path: state });
  await setup.close();

  const context = await browser.newContext({
    viewport: { width: 960, height: 600 },
    locale: 'pt-PT',
    timezoneId: 'Europe/Lisbon',
    storageState: state,
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  await page.route('**/api/documents**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    const json = await response.json();
    const body = Array.isArray(json.documents)
      ? { ...json, documents: json.documents.map(paint) }
      : paint(json);
    await route.fulfill({
      response,
      body: JSON.stringify(body),
      headers: { ...response.headers(), 'content-type': 'application/json' },
    });
  });

  const scenes = [];
  const mark = async (name, ms, required) => {
    const started = Date.now() - startedAt;
    await page.waitForTimeout(ms);
    const shot = join(work, `${name}.png`);
    await page.screenshot({ path: shot });
    const lines = [...(await visibleLines(page)), readPicture(shot)];
    const text = assertClean(name, lines);
    for (const phrase of required) {
      if (!text.toLowerCase().includes(phrase.toLowerCase())) {
        throw new Error(`${name} missing ${phrase}\n${text}`);
      }
    }
    scenes.push({ name, start: started, end: Date.now() - startedAt, lines });
  };

  await page.goto(`${app}/upload`);
  await page.getByText('Fotografar').waitFor();
  const existing = await callApi(page, '/api/documents');
  for (const item of existing.body?.documents || []) {
    await callApi(page, `/api/documents/${item.id}`, { method: 'DELETE' });
  }
  const startedAt = Date.now();
  await mark('upload', 2500, ['Fotografar', 'Carregar PDF ou foto']);

  await page.locator('input[type="file"]').last().setInputFiles(invoice);
  await mark('preview', 2500, ['Exemplo, Lda', 'IVA estimativa', '23,00']);

  await page.getByRole('button', { name: 'Carregar', exact: true }).click();
  await page.getByText('Carregado').waitFor();
  await mark('uploaded', 200, ['Carregado']);

  let documentId = null;
  for (let attempt = 0; attempt < 40 && !documentId; attempt += 1) {
    const listed = await callApi(page, '/api/documents');
    const found = listed.body?.documents?.find((item) => item.status !== 'processing');
    if (found) documentId = found.id;
    else await page.waitForTimeout(250);
  }
  if (!documentId) throw new Error('receipt did not finish reading');
  const patched = await callApi(page, `/api/documents/${documentId}`, { method: 'PATCH', body: receipt });
  if (patched.status !== 200) throw new Error(`patch failed ${patched.status} ${JSON.stringify(patched.body)}`);

  await page.goto(`${app}/receipts/${documentId}`);
  await page.getByText('Exemplo, Lda').waitFor();
  await mark('review', 3500, ['exemplo ilustrativo', 'Exemplo, Lda', 'IVA estimativa', '23,00']);

  await page.goto(`${app}/summary`);
  await page.getByText('IVA estimado').waitFor();
  await showEstimate(page);
  await mark('deadline-q4', 2500, [q4Deadline, 'Este valor ignora']);

  await page.evaluate(() => window.scrollTo(0, 0));
  for (let step = 0; step < 3; step += 1) {
    await page.getByRole('button', { name: 'Período anterior' }).click();
    await page.waitForTimeout(200);
  }
  await page.getByText('T1 2026', { exact: true }).waitFor();
  await showEstimate(page);
  await mark('estimate-q1', 3000, [q1Deadline, 'Este valor ignora', '23,00']);

  const packBox = await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')].find((node) =>
      (node.textContent || '').includes('Enviar ao Contabilista'),
    );
    const top = button.getBoundingClientRect().top + window.scrollY;
    window.scrollTo(0, Math.max(0, top - 120));
    const rect = button.getBoundingClientRect();
    return { top: rect.top, bottom: rect.bottom, height: rect.height, text: button.innerText };
  });
  if (packBox.top < 56 || packBox.bottom > 540) {
    throw new Error(`pack button outside the frame ${JSON.stringify(packBox)}`);
  }
  await mark('pack', 2000, ['Enviar ao Contabilista']);

  await context.close();
  const mp4 = join(site, 'assets/demo-short.mp4');
  const list = scenes
    .map((scene) => {
      const seconds = Math.max(0.2, (scene.end - scene.start) / 1000);
      return `file '${join(work, `${scene.name}.png`)}'\nduration ${seconds.toFixed(3)}`;
    })
    .join('\n');
  const last = scenes[scenes.length - 1];
  const concat = `${list}\nfile '${join(work, `${last.name}.png`)}'\n`;
  const listPath = join(work, 'scenes.txt');
  writeFileSync(listPath, concat);
  const encoded = spawnSync(
    'ffmpeg',
    ['-y', '-f', 'concat', '-safe', '0', '-i', listPath, '-vf', 'fps=25,format=yuv420p', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-movflags', '+faststart', mp4],
    { encoding: 'utf8' },
  );
  if (encoded.status !== 0) throw new Error(encoded.stderr || 'mp4 encode failed');

  const posterSource = join(work, 'estimate-q1.png');
  const poster = spawnSync(
    'ffmpeg',
    ['-y', '-i', posterSource, '-q:v', '3', join(site, 'assets/poster.jpg')],
    { encoding: 'utf8' },
  );
  if (poster.status !== 0) throw new Error(poster.stderr || 'poster failed');

  const frames = ['upload', 'review', 'estimate-q1'];
  const frameDir = process.env.DEMO_FRAME_DIR || '/opt/cursor/artifacts/demo-frames';
  mkdirSync(frameDir, { recursive: true });
  for (const name of frames) {
    const saved = spawnSync(
      'ffmpeg',
      ['-y', '-i', join(work, `${name}.png`), '-q:v', '3', join(frameDir, `${name}.jpg`)],
      { encoding: 'utf8' },
    );
    if (saved.status !== 0) throw new Error(saved.stderr || `frame ${name} failed`);
  }

  const timeline = videoTimeline(scenes);
  const tracks = captionFiles(timeline);
  writeFileSync(join(site, 'assets/captions-pt.vtt'), tracks.pt);
  writeFileSync(join(site, 'assets/captions-en.vtt'), tracks.en);
  writeFileSync(join(site, 'assets/demo-timeline.json'), `${JSON.stringify(timeline, null, 2)}\n`);
  writeFileSync(join(work, 'scenes.json'), JSON.stringify(scenes, null, 2));
  await browser.close();
  console.log(JSON.stringify({ mp4, frameDir, scenes: scenes.map(({ name, start, end }) => ({ name, start, end })) }));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
