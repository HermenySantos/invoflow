const REGIMES = new Set(['trimestral', 'mensal', 'nao_sei']);
const VOLUMES = new Set(['lt20', '20-100', 'gt100']);
const ACCOUNTANTS = new Set(['sim', 'nao']);

const QUALIFIED_VOLUMES = new Set(['20-100', 'gt100']);

export function isQualified(answers) {
  return (
    answers.regime === 'trimestral' &&
    QUALIFIED_VOLUMES.has(answers.volume) &&
    answers.accountant === 'sim'
  );
}

export function emailOk(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function parseAnswers(raw) {
  const name = String(raw.name ?? '').trim();
  const email = String(raw.email ?? '').trim();
  const regime = String(raw.regime ?? '');
  const volume = String(raw.volume ?? '');
  const accountant = String(raw.accountant ?? '');
  const consent = raw.consent === true || raw.consent === 'on';

  if (!name || name.length > 200) return null;
  if (!emailOk(email) || email.length > 200) return null;
  if (!REGIMES.has(regime) || !VOLUMES.has(volume) || !ACCOUNTANTS.has(accountant)) return null;
  if (!consent) return null;

  const answers = { name, email, regime, volume, accountant, consent };
  return { ...answers, qualified: isQualified(answers) };
}

export function readUtm(params) {
  const pick = (key) => String(params.get(key) ?? '').trim().slice(0, 200);
  return {
    utm_source: pick('utm_source'),
    utm_medium: pick('utm_medium'),
    utm_campaign: pick('utm_campaign'),
  };
}
