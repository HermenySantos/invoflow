import { parseAnswers } from '../../js/qualify.js';

function text(value) {
  return String(value ?? '').trim().slice(0, 200);
}

export async function onRequestPost({ request, env }) {
  let raw;
  try {
    raw = await request.json();
  } catch {
    return Response.json({ ok: false, error: 'invalid' }, { status: 400 });
  }

  const answers = parseAnswers(raw);
  if (!answers) {
    return Response.json({ ok: false, error: 'invalid' }, { status: 400 });
  }

  const record = {
    ...answers,
    utm_source: text(raw.utm_source),
    utm_medium: text(raw.utm_medium),
    utm_campaign: text(raw.utm_campaign),
    lang: raw.lang === 'en' ? 'en' : 'pt',
    receivedAt: new Date().toISOString(),
  };

  if (env?.SIGNUPS && typeof env.SIGNUPS.put === 'function') {
    const id = crypto.randomUUID();
    await env.SIGNUPS.put(id, JSON.stringify(record));
    return Response.json({ ok: true, id });
  }

  if (env?.DB && typeof env.DB.prepare === 'function') {
    const id = crypto.randomUUID();
    await env.DB.prepare('INSERT INTO signups (id, payload, received_at) VALUES (?, ?, ?)').bind(
      id,
      JSON.stringify(record),
      record.receivedAt,
    ).run();
    return Response.json({ ok: true, id });
  }

  return Response.json({ ok: false, error: 'no binding' }, { status: 501 });
}
