import { withSecurity, withoutSMaxAge } from '../security.js';

function parseRange(header, size) {
  const match = /^bytes=(\d*)-(\d*)$/i.exec(header.trim());
  if (!match) return null;
  const [, startText, endText] = match;
  if (startText === '' && endText === '') return null;
  if (startText === '') {
    const suffix = Number(endText);
    if (suffix <= 0) return null;
    const length = Math.min(suffix, size);
    return { start: size - length, end: size - 1 };
  }
  const start = Number(startText);
  const end = endText === '' ? size - 1 : Number(endText);
  if (start >= size || start > end) return null;
  return { start, end: Math.min(end, size - 1) };
}

function withLength(headers, length) {
  const next = new Headers(headers);
  next.delete('content-encoding');
  next.delete('content-length');
  next.set('accept-ranges', 'bytes');
  next.set('content-length', String(length));
  return withSecurity(next);
}

export async function onRequest({ request, env }) {
  const url = new URL(request.url);
  if (!url.pathname.toLowerCase().endsWith('.mp4')) return withoutSMaxAge(await env.ASSETS.fetch(request));
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return withoutSMaxAge(new Response(null, { status: 405, headers: withSecurity({ allow: 'GET, HEAD' }) }));
  }

  const assetUrl = new URL(request.url);
  const asset = await env.ASSETS.fetch(new Request(assetUrl, { method: 'GET' }));
  if (!asset.ok) return withoutSMaxAge(asset);

  const bytes = new Uint8Array(await asset.arrayBuffer());
  const size = bytes.byteLength;
  const range = request.headers.get('range');
  if (!range) {
    const headers = withLength(asset.headers, size);
    return withoutSMaxAge(new Response(request.method === 'HEAD' ? null : bytes, { status: 200, headers }));
  }

  const parsed = parseRange(range, size);
  if (!parsed) {
    const headers = withLength(asset.headers, 0);
    headers.set('content-range', `bytes */${size}`);
    return withoutSMaxAge(new Response(null, { status: 416, headers }));
  }

  const slice = bytes.subarray(parsed.start, parsed.end + 1);
  const headers = withLength(asset.headers, slice.byteLength);
  headers.set('content-range', `bytes ${parsed.start}-${parsed.end}/${size}`);
  return withoutSMaxAge(new Response(request.method === 'HEAD' ? null : slice, { status: 206, headers }));
}
