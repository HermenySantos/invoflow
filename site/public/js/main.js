import { CONFIG } from './config.js';
import { copy } from './copy.js';
import { readUtm } from './qualify.js';
import { mountAnalytics, track } from './analytics.js';

const LANG_KEY = 'invoflow_demand_lang';
const CLOSED_LOG = 'FORM_ENDPOINT is empty. The form is not sent and nothing is stored.';

const fields = [
  ['email', 'errorEmailEmpty'],
  ['consent', 'errorConsent'],
];

let lang = 'pt';

function t(key) {
  return copy[lang][key];
}

function applyCopy() {
  document.documentElement.lang = lang === 'en' ? 'en' : 'pt-PT';
  document.title = t('metaTitle');
  const description = document.querySelector('meta[name="description"]');
  if (description) description.setAttribute('content', t('metaDescription'));
  const ogTitle = document.querySelector('meta[property="og:title"]');
  const ogDescription = document.querySelector('meta[property="og:description"]');
  if (ogTitle) ogTitle.setAttribute('content', t('ogTitle'));
  if (ogDescription) ogDescription.setAttribute('content', t('ogDescription'));
  document.querySelectorAll('[data-i18n]').forEach((node) => {
    if (node.children.length) return;
    const value = t(node.dataset.i18n);
    if (value != null) node.textContent = value;
  });
  document.querySelectorAll('[data-i18n-attr]').forEach((node) => {
    const [attr, key] = node.dataset.i18nAttr.split(':');
    const value = t(key);
    if (attr && value != null) node.setAttribute(attr, value);
  });
  document.querySelectorAll('.lang__opt').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.lang === lang));
  });
  const video = document.querySelector('#demo-video');
  if (!video) return;
  const code = lang === 'en' ? 'en' : 'pt';
  video.querySelectorAll('track').forEach((track) => {
    if (track.getAttribute('srclang') === code) track.setAttribute('default', '');
    else track.removeAttribute('default');
  });
  [...video.textTracks].forEach((track) => {
    track.mode = track.language === code ? 'showing' : 'disabled';
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

function clearField(name) {
  const slot = document.querySelector(`[data-error-for="${name}"]`);
  if (slot) slot.textContent = '';
  const field = document.getElementById(name);
  if (field) field.removeAttribute('aria-invalid');
}

function fieldMessage(form, name) {
  if (name === 'email') {
    const value = form.email.value.trim();
    if (!value) return t('errorEmailEmpty');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return t('errorEmailInvalid');
  }
  if (name === 'consent' && !form.consent.checked) return t('errorConsent');
  return '';
}

function collect(form) {
  return {
    email: form.email.value,
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

  const answers = collect(form);
  const utm = {
    utm_source: form.utm_source.value,
    utm_medium: form.utm_medium.value,
    utm_campaign: form.utm_campaign.value,
  };
  const payload = { email: answers.email, consent: true, ...utm, lang, extra: form.extra.value };

  track('form_submit');

  if (!CONFIG.FORM_ENDPOINT) {
    console.info(CLOSED_LOG);
    return;
  }

  const button = document.querySelector('#submit-pilot');
  const sending = document.querySelector('#sending');
  button.disabled = true;
  form.setAttribute('aria-busy', 'true');
  if (sending) sending.textContent = t('sending');
  try {
    const response = await fetch(CONFIG.FORM_ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (response.status === 429 || !response.ok) {
      showError('form', t('errorSend'));
      button.disabled = false;
      form.removeAttribute('aria-busy');
      if (sending) sending.textContent = '';
      return;
    }
    form.removeAttribute('aria-busy');
    if (sending) sending.textContent = '';
    showThanks();
  } catch {
    showError('form', t('errorSend'));
    button.disabled = false;
    form.removeAttribute('aria-busy');
    if (sending) sending.textContent = '';
  }
}

function mountVideo() {
  const video = document.querySelector('#demo-video');
  const play = document.querySelector('#demo-play');
  if (!video || !play) return;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) {
    video.removeAttribute('autoplay');
    video.pause();
  }
  const stage = video.parentElement;
  video.removeAttribute('controls');
  play.hidden = false;
  stage.classList.add('is-idle');
  const start = () => {
    play.hidden = true;
    stage.classList.remove('is-idle');
    video.setAttribute('controls', '');
  };
  play.addEventListener('click', () => {
    video.muted = true;
    start();
    video.play();
    video.focus();
  });
  video.addEventListener('play', start);
}

function mountUtm() {
  const utm = readUtm(new URLSearchParams(window.location.search));
  const form = document.querySelector('#pilot-form');
  form.utm_source.value = utm.utm_source;
  form.utm_medium.value = utm.utm_medium;
  form.utm_campaign.value = utm.utm_campaign;
}

function mountLiveErrors(form) {
  form.email.addEventListener('input', () => {
    if (!form.email.hasAttribute('aria-invalid')) return;
    if (!fieldMessage(form, 'email')) clearField('email');
  });
  form.consent.addEventListener('change', () => {
    if (!form.consent.hasAttribute('aria-invalid')) return;
    if (!fieldMessage(form, 'consent')) clearField('consent');
  });
}

function mountClosed() {
  const notice = document.querySelector('#closed-notice');
  const button = document.querySelector('#submit-pilot');
  const formset = document.querySelector('#formset');
  const closed = !CONFIG.FORM_ENDPOINT;
  notice.hidden = !closed;
  button.disabled = closed;
  if (formset) formset.disabled = closed;
  if (closed) console.info(CLOSED_LOG);
}

function mountMasthead() {
  const head = document.querySelector('.masthead');
  if (!head) return;
  const onScroll = () => head.classList.toggle('is-scrolled', window.scrollY > 8);
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

function mountReveal() {
  const reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-in');
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.12 },
    );
    reveals.forEach((node) => observer.observe(node));
  } else {
    reveals.forEach((node) => node.classList.add('is-in'));
  }
  document.documentElement.classList.add('js');
}

document.querySelectorAll('.lang__opt').forEach((button) => {
  button.addEventListener('click', () => setLang(button.dataset.lang));
});

document.querySelectorAll('[data-cta]').forEach((node) => {
  node.addEventListener('click', () => track('cta_click'));
});

const pilotForm = document.querySelector('#pilot-form');
pilotForm.addEventListener('submit', (event) => {
  event.preventDefault();
  submitForm(event.currentTarget);
});
mountLiveErrors(pilotForm);

const queryLang = new URLSearchParams(window.location.search).get('lang');
try {
  const stored = localStorage.getItem(LANG_KEY);
  if (queryLang === 'en' || queryLang === 'pt') lang = queryLang;
  else if (stored === 'en' || stored === 'pt') lang = stored;
} catch {
  if (queryLang === 'en' || queryLang === 'pt') lang = queryLang;
}

applyCopy();
mountVideo();
mountUtm();
mountClosed();
mountMasthead();
mountReveal();
mountAnalytics();
track('visit');
