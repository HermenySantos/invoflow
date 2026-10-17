import { CONFIG } from './config.js';
import { copy } from './copy.js';
import { parseAnswers, readUtm } from './qualify.js';
import { mountAnalytics, track } from './analytics.js';

const LANG_KEY = 'invoflow_demand_lang';
const CLOSED_LOG = 'FORM_ENDPOINT is empty. The form is not sent and nothing is stored.';

const fields = [
  ['name', 'errorName'],
  ['email', 'errorEmail'],
  ['regime', 'errorRegime'],
  ['volume', 'errorVolume'],
  ['accountant', 'errorAccountant'],
  ['consent', 'errorConsent'],
];

let lang = 'pt';

function t(key) {
  return copy[lang][key];
}

function applyCopy() {
  document.documentElement.lang = lang;
  document.title = t('metaTitle');
  const description = document.querySelector('meta[name="description"]');
  if (description) description.setAttribute('content', t('metaDescription'));
  document.querySelectorAll('[data-i18n]').forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
}

function setLang(next) {
  lang = next === 'en' ? 'en' : 'pt';
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch (error) {
    if (!(error instanceof DOMException)) throw error;
  }
  applyCopy();
  clearErrors();
}

function selected(form, name) {
  const node = form.querySelector(`input[name="${name}"]:checked`);
  return node ? node.value : '';
}

function showError(name, message) {
  const slot = document.querySelector(`[data-error-for="${name}"]`);
  if (!slot) return;
  slot.textContent = message;
  const field = document.getElementById(name) || document.querySelector(`[name="${name}"]`);
  if (field) field.setAttribute('aria-invalid', 'true');
}

function clearErrors() {
  document.querySelectorAll('[data-error-for]').forEach((slot) => {
    slot.textContent = '';
  });
  document.querySelectorAll('[aria-invalid="true"]').forEach((field) => {
    field.removeAttribute('aria-invalid');
  });
}

function fieldMessage(form, name) {
  if (name === 'name' && !form.name.value.trim()) return t('errorName');
  if (name === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.value.trim())) return t('errorEmail');
  if (name === 'regime' && !selected(form, 'regime')) return t('errorRegime');
  if (name === 'volume' && !selected(form, 'volume')) return t('errorVolume');
  if (name === 'accountant' && !selected(form, 'accountant')) return t('errorAccountant');
  if (name === 'consent' && !form.consent.checked) return t('errorConsent');
  return '';
}

function collect(form) {
  return {
    name: form.name.value,
    email: form.email.value,
    regime: selected(form, 'regime'),
    volume: selected(form, 'volume'),
    accountant: selected(form, 'accountant'),
    consent: form.consent.checked,
  };
}

function showThanks() {
  document.querySelector('#pilot-form').hidden = true;
  const thanks = document.querySelector('#thanks');
  thanks.hidden = false;
  thanks.focus();
}

async function submitForm(form) {
  clearErrors();
  let first = null;
  for (const [name] of fields) {
    const message = fieldMessage(form, name);
    if (!message) continue;
    showError(name, message);
    if (!first) first = name;
  }
  if (first) {
    const field = document.getElementById(first) || document.querySelector(`[name="${first}"]`);
    field?.focus();
    return;
  }

  const answers = parseAnswers(collect(form));
  if (!answers) return;

  const utm = {
    utm_source: form.utm_source.value,
    utm_medium: form.utm_medium.value,
    utm_campaign: form.utm_campaign.value,
  };
  const payload = { ...answers, ...utm, lang, extra: form.extra.value };

  track('form_submit');
  if (answers.qualified) track('qualified_submit');

  if (!CONFIG.FORM_ENDPOINT) {
    console.info(CLOSED_LOG);
    return;
  }

  const button = document.querySelector('#submit-pilot');
  button.disabled = true;
  try {
    const response = await fetch(CONFIG.FORM_ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (response.status === 429) {
      let message = t('errorSend');
      try {
        const body = await response.json();
        if (body?.message?.[lang]) message = body.message[lang];
      } catch {
        message = t('errorSend');
      }
      showError('form', message);
      button.disabled = false;
      return;
    }
    if (!response.ok) throw new Error('request failed');
    showThanks();
  } catch {
    showError('form', t('errorSend'));
    button.disabled = false;
  }
}

function mountDeposit() {
  const slot = document.querySelector('#deposit');
  if (!CONFIG.DEPOSIT_ENABLED || !CONFIG.STRIPE_PAYMENT_LINK) {
    slot.replaceChildren();
    return;
  }
  const paragraph = document.createElement('p');
  paragraph.className = 'deposit';
  paragraph.dataset.i18n = 'deposit';
  paragraph.textContent = t('deposit');
  const link = document.createElement('a');
  link.href = CONFIG.STRIPE_PAYMENT_LINK;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.dataset.i18n = 'depositLink';
  link.textContent = t('depositLink');
  slot.replaceChildren(paragraph, link);
}

function mountVideo() {
  const video = document.querySelector('#demo-video');
  if (!video) return;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) {
    video.removeAttribute('autoplay');
    video.pause();
  }
}

function mountUtm() {
  const utm = readUtm(new URLSearchParams(window.location.search));
  const form = document.querySelector('#pilot-form');
  form.utm_source.value = utm.utm_source;
  form.utm_medium.value = utm.utm_medium;
  form.utm_campaign.value = utm.utm_campaign;
}

function mountClosed() {
  const notice = document.querySelector('#closed-notice');
  const button = document.querySelector('#submit-pilot');
  const closed = !CONFIG.FORM_ENDPOINT;
  notice.hidden = !closed;
  button.disabled = closed;
  if (closed) console.info(CLOSED_LOG);
}

document.querySelector('#lang-toggle').addEventListener('click', () => {
  setLang(lang === 'pt' ? 'en' : 'pt');
});

document.querySelectorAll('[data-cta]').forEach((node) => {
  node.addEventListener('click', () => track('cta_click'));
});

document.querySelector('#pilot-form').addEventListener('submit', (event) => {
  event.preventDefault();
  submitForm(event.currentTarget);
});

try {
  const stored = localStorage.getItem(LANG_KEY);
  if (stored === 'en' || stored === 'pt') lang = stored;
} catch {
  lang = 'pt';
}

applyCopy();
mountDeposit();
mountVideo();
mountUtm();
mountClosed();
mountAnalytics();
track('visit');
