import { parseAnswers } from '../../public/js/qualify.js';

const MAX_BODY = 8192;
const LIMIT = 5;
const WINDOW_MS = 60 * 60 * 1000;
const OK_BODY = '{"ok":true}';

const DELETE_STALE =
  'DELETE FROM signup_rates WHERE reset_at <= ? AND ip_hash != ?';

const UPSERT_RATE = `INSERT INTO signup_rates (ip_hash, count, reset_at)
VALUES (?, 1, ?)
ON CONFLICT(ip_hash) DO UPDATE SET
  count = CASE WHEN signup_rates.reset_at <= ? THEN 1 ELSE signup_rates.count + 1 END,
  reset_at = CASE WHEN signup_rates.reset_at <= ? THEN excluded.reset_at ELSE signup_rates.reset_at END
RETURNING count, reset_at`;

const INSERT_SIGNUP = `INSERT INTO signups (id, email, payload, received_at)
SELECT ?, ?, ?, ?
WHERE ? = 1 AND NOT EXISTS (SELECT 1 FROM signups WHERE email = ?)`;

const RATE_MESSAGE = {
  pt: 'Muitos pedidos. Tente outra vez dentro de uma hora.',
  en: 'Too many requests. Try again within an hour.',
};

function reply(status, body) {
  return new Response(status === 200 ? OK_BODY : JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'x-content-type-options': 'nosniff',
      'cache-control': 'no-store',
    },
  });
}

function text(value) {
  return String(value ?? '').trim().slice(0, 200);
}

function jsonType(request) {
  const media = (request.headers.get('content-type') ?? '').split(';')[0].trim().toLowerCase();
  return media === 'application/json';
}

function originAllowed(request, env) {
  const header = request.headers.get('origin');
  if (!header) return false;
  let parsed;
  try {
    parsed = new URL(header);
  } catch {
    return false;
  }
  if (parsed.origin !== header) return false;
  const allow = String(env.SIGNUP_ORIGINS ?? '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  if (allow.length > 0) return allow.includes(header);
  return parsed.host === new URL(request.url).host;
}

function ipv4(value) {
  const parts = value.split('.');
  if (parts.length !== 4) return null;
  const numbers = [];
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return null;
    const number = Number(part);
    if (number > 255) return null;
    numbers.push(String(number));
  }
  return numbers.join('.');
}

function expandV6(value) {
  const halves = value.split('::');
  if (halves.length > 2) return null;
  const left = halves[0] ? halves[0].split(':') : [];
  const right = halves.length === 2 && halves[1] ? halves[1].split(':') : [];
  if (halves.length === 1 && left.length !== 8) return null;
  const missing = 8 - left.length - right.length;
  if (halves.length === 2 && missing < 1) return null;
  if (missing < 0) return null;
  const groups = [...left, ...Array(missing).fill('0'), ...right];
  if (groups.length !== 8) return null;
  const expanded = [];
  for (const group of groups) {
    if (!/^[0-9a-f]{1,4}$/.test(group)) return null;
    expanded.push(group.padStart(4, '0'));
  }
  return expanded;
}

function bucketIp(ip) {
  const bare = ip.trim().toLowerCase().split('%')[0].replace(/^\[|\]$/g, '');
  const mapped = bare.match(/^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/);
  if (mapped) return ipv4(mapped[1]);
  if (bare.includes('.')) return ipv4(bare);
  const groups = expandV6(bare);
  if (!groups) return null;
  if (groups.slice(0, 6).join(':') === '0000:0000:0000:0000:0000:ffff') {
    const high = Number.parseInt(groups[6], 16);
    const low = Number.parseInt(groups[7], 16);
    return `${high >> 8}.${high & 255}.${low >> 8}.${low & 255}`;
  }
  return groups.slice(0, 4).join(':');
}

function normalizeEmail(value) {
  const normalized = String(value ?? '').normalize('NFKC').trim().toLowerCase();
  const at = normalized.lastIndexOf('@');
  if (at <= 0) return normalized;
  let domain = normalized.slice(at + 1);
  if (domain.endsWith('.')) domain = domain.slice(0, -1);
  try {
    domain = new URL(`http://${domain}`).hostname;
  } catch {
    return normalized;
  }
  return `${normalized.slice(0, at)}@${domain}`;
}

async function hashBucket(bucket, secret) {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const digest = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(bucket));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function recordFrom(raw, answers) {
  return {
    name: answers.name,
    email: answers.email,
    regime: answers.regime,
    volume: answers.volume,
    accountant: answers.accountant,
    consent: true,
    qualified: answers.qualified,
    utm_source: text(raw.utm_source),
    utm_medium: text(raw.utm_medium),
    utm_campaign: text(raw.utm_campaign),
    lang: raw.lang === 'en' ? 'en' : 'pt',
    receivedAt: new Date().toISOString(),
  };
}

export async function onRequestPost({ request, env }) {
  const secret = String(env?.IP_HASH_SECRET ?? '').trim();
  const db = env?.DB;
  if (!secret || typeof db?.prepare !== 'function') return reply(501, { ok: false });
  if (!jsonType(request)) return reply(400, { ok: false });
  if (!originAllowed(request, env)) return reply(403, { ok: false });

  const ip = request.headers.get('cf-connecting-ip')?.trim() ?? '';
  const bucket = ip ? bucketIp(ip) : null;
  if (!bucket) return reply(400, { ok: false });

  const bytes = await request.arrayBuffer();
  if (bytes.byteLength > MAX_BODY) return reply(413, { ok: false });

  let raw;
  try {
    raw = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  } catch {
    return reply(400, { ok: false });
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return reply(400, { ok: false });

  const honeypot = text(raw.extra) !== '';
  const answers = honeypot ? null : parseAnswers({ ...raw, email: normalizeEmail(raw.email) });
  if (!honeypot && !answers) return reply(400, { ok: false });

  const now = Date.now();
  const hash = await hashBucket(bucket, secret);
  const record = answers ? recordFrom(raw, answers) : null;
  await db.prepare(DELETE_STALE).bind(now, hash).run();
  const rate = await db.prepare(UPSERT_RATE).bind(hash, now + WINDOW_MS, now, now).first();
  const allowed = Number(rate?.count) <= LIMIT;
  const write = honeypot || !allowed ? 0 : 1;
  try {
    await db
      .prepare(INSERT_SIGNUP)
      .bind(
        crypto.randomUUID(),
        record?.email ?? '',
        record ? JSON.stringify(record) : '{}',
        record?.receivedAt ?? new Date().toISOString(),
        write,
        record?.email ?? '',
      )
      .run();
  } catch (error) {
    if (!String(error?.message || '').includes('UNIQUE')) throw error;
  }

  if (honeypot || allowed) return reply(200);
  return reply(429, { ok: false, message: RATE_MESSAGE });
}
