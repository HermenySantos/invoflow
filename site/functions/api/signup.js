import { parseAnswers } from '../../js/qualify.js';

const MAX_BODY = 8192;
const LIMIT = 5;
const WINDOW_MS = 60 * 60 * 1000;
const HONEYPOT = 'leave_blank';

function text(value) {
  return String(value ?? '').trim().slice(0, 200);
}

function clientIp(request) {
  const direct = request.headers.get('cf-connecting-ip');
  if (direct) return direct.trim();
  const forwarded = request.headers.get('x-forwarded-for');
  if (forwarded) return forwarded.split(',')[0].trim();
  return 'unknown';
}

async function hashIp(ip) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(ip));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function decide(current, now) {
  if (!current || now >= current.resetAt) {
    return { limited: false, next: { count: 1, resetAt: now + WINDOW_MS } };
  }
  if (current.count >= LIMIT) return { limited: true, next: null };
  return { limited: false, next: { count: current.count + 1, resetAt: current.resetAt } };
}

function kvStore(namespace) {
  return {
    async limited(hash, now) {
      const key = `rate:${hash}`;
      let current = null;
      const raw = await namespace.get(key);
      if (raw) {
        try {
          current = JSON.parse(raw);
        } catch {
          current = null;
        }
      }
      const decision = decide(current, now);
      if (decision.next) {
        const ttl = Math.max(60, Math.ceil((decision.next.resetAt - now) / 1000));
        await namespace.put(key, JSON.stringify(decision.next), { expirationTtl: ttl });
      }
      return decision.limited;
    },
    async hasEmail(email) {
      return Boolean(await namespace.get(`email:${email}`));
    },
    async save(id, record) {
      await namespace.put(id, JSON.stringify(record));
      await namespace.put(`email:${record.email}`, id);
    },
  };
}

function d1Store(db) {
  return {
    async limited(hash, now) {
      const row = await db
        .prepare('SELECT count, reset_at FROM signup_rates WHERE ip_hash = ?')
        .bind(hash)
        .first();
      const current = row ? { count: Number(row.count), resetAt: Number(row.reset_at) } : null;
      const decision = decide(current, now);
      if (!decision.next) return true;
      if (!current || now >= current.resetAt) {
        await db
          .prepare(
            'INSERT INTO signup_rates (ip_hash, count, reset_at) VALUES (?, ?, ?) ON CONFLICT(ip_hash) DO UPDATE SET count = excluded.count, reset_at = excluded.reset_at',
          )
          .bind(hash, decision.next.count, decision.next.resetAt)
          .run();
      } else {
        await db.prepare('UPDATE signup_rates SET count = ? WHERE ip_hash = ?').bind(decision.next.count, hash).run();
      }
      return false;
    },
    async hasEmail(email) {
      const row = await db.prepare('SELECT id FROM signups WHERE email = ?').bind(email).first();
      return Boolean(row);
    },
    async save(id, record) {
      await db
        .prepare('INSERT INTO signups (id, email, payload, received_at) VALUES (?, ?, ?, ?)')
        .bind(id, record.email, JSON.stringify(record), record.receivedAt)
        .run();
    },
  };
}

function openStore(env) {
  if (env?.SIGNUPS && typeof env.SIGNUPS.get === 'function' && typeof env.SIGNUPS.put === 'function') {
    return kvStore(env.SIGNUPS);
  }
  if (env?.DB && typeof env.DB.prepare === 'function') return d1Store(env.DB);
  return null;
}

function thanks() {
  return Response.json({ ok: true });
}

export async function onRequestPost({ request, env }) {
  const rawText = await request.text();
  if (rawText.length > MAX_BODY) {
    return Response.json({ ok: false, error: 'invalid' }, { status: 413 });
  }

  let raw;
  try {
    raw = JSON.parse(rawText);
  } catch {
    return Response.json({ ok: false, error: 'invalid' }, { status: 400 });
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return Response.json({ ok: false, error: 'invalid' }, { status: 400 });
  }
  if (text(raw[HONEYPOT]) !== '') return thanks();

  const answers = parseAnswers(raw);
  if (!answers) return Response.json({ ok: false, error: 'invalid' }, { status: 400 });

  const record = {
    name: answers.name,
    email: answers.email.toLowerCase(),
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

  const store = openStore(env);
  if (!store) return Response.json({ ok: false, error: 'no binding' }, { status: 501 });

  if (await store.limited(await hashIp(clientIp(request)), Date.now())) {
    return Response.json({ ok: false, error: 'rate' }, { status: 429 });
  }
  if (await store.hasEmail(record.email)) return thanks();

  const id = crypto.randomUUID();
  try {
    await store.save(id, record);
  } catch (error) {
    if (String(error?.message || '').includes('UNIQUE')) return thanks();
    throw error;
  }
  return Response.json({ ok: true, id });
}
