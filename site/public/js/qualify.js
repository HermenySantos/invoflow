export function readUtm(params) {
  const pick = (key) => String(params.get(key) ?? '').trim().slice(0, 200);
  return {
    utm_source: pick('utm_source'),
    utm_medium: pick('utm_medium'),
    utm_campaign: pick('utm_campaign'),
  };
}
