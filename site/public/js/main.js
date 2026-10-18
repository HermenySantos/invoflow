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
  const details = document.querySelector('#demonstracao');
  document.querySelectorAll('[data-open-video]').forEach((link) => {
    link.addEventListener('click', () => {
      if (details) details.open = true;
    });
  });
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

function mountHero() {
  const stage = document.querySelector('#stage');
  if (!stage) return;
  const motionOK = window.matchMedia('(prefers-reduced-motion: no-preference)').matches;
  const replay = document.querySelector('#replay');
  if (!motionOK) {
    stage.classList.add('is-done');
    return;
  }
  const pile = stage.querySelector('.pile');
  const cards = [...stage.querySelectorAll('.rcpt')];
  const rows = [...stage.querySelectorAll('[data-row]')];
  const foot = (key) => stage.querySelector(`[data-foot="${key}"]`);
  const vExp = document.querySelector('#v-exp');
  const vSales = document.querySelector('#v-sales');
  const vTotal = document.querySelector('#v-total');
  const dbl = stage.querySelector('.dbl');
  const pack = stage.querySelector('.sheet__pack');
  const VAT = [23, 4.6, 11.5, 2.76];
  const SALES = '230,00';
  const EXP = 41.86;
  const TOTAL = 188.14;
  const fmt = (n) => n.toFixed(2).replace('.', ',');
  const minus = '\u2212 ';
  const T0 = 380;
  const GAP = 620;
  const FLY = 760;
  const WRITE_AT = 520;
  const CELL = 55;
  const WRITE = 420;
  const SPRING = 'cubic-bezier(.34,1.56,.64,1)';
  const OUT = 'cubic-bezier(.22,1,.36,1)';
  const IO = 'cubic-bezier(.65,0,.35,1)';
  let anims = [];
  let timers = [];
  let run = 0;
  const animate = (el, frames, options) => {
    const animation = el.animate(frames, { fill: 'both', ...options });
    anims.push(animation);
    return animation;
  };
  const at = (ms, fn) => timers.push(setTimeout(fn, ms));
  const count = (el, from, to, dur, prefix, id) => {
    const t0 = performance.now();
    const step = (now) => {
      if (id !== run) return;
      const p = Math.min(1, (now - t0) / dur);
      const eased = 1 - (1 - p) ** 3;
      el.textContent = prefix + fmt(from + (to - from) * eased);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  const writeCells = (tr, delay) => {
    [...tr.children].forEach((cell, index) => {
      animate(
        cell,
        [
          { opacity: 0, clipPath: 'inset(0 100% 0 0)' },
          { opacity: 1, clipPath: 'inset(0 0% 0 0)' },
        ],
        { duration: WRITE, delay: delay + index * CELL, easing: OUT },
      );
    });
  };
  const finish = () => {
    anims.forEach((animation) => animation.cancel());
    anims = [];
    vExp.textContent = minus + fmt(EXP);
    vSales.textContent = SALES;
    vTotal.textContent = fmt(TOTAL);
    stage.classList.add('is-done');
    stage.classList.remove('is-live');
    stage.removeAttribute('aria-busy');
    if (replay) replay.hidden = false;
  };
  const play = () => {
    const id = ++run;
    anims.forEach((animation) => animation.cancel());
    anims = [];
    timers.forEach(clearTimeout);
    timers = [];
    stage.classList.remove('is-done');
    stage.classList.add('is-live');
    stage.setAttribute('aria-busy', 'true');
    if (replay) replay.hidden = true;
    vExp.textContent = minus + fmt(0);
    vSales.textContent = '\u00a0';
    vTotal.textContent = fmt(0);
    const pileBox = pile.getBoundingClientRect();
    let sub = 0;
    cards.forEach((card, index) => {
      const rowBox = rows[index].getBoundingClientRect();
      const cx = pileBox.left + card.offsetLeft + card.offsetWidth / 2;
      const cy = pileBox.top + card.offsetTop + card.offsetHeight / 2;
      const tx = Math.round(rowBox.left + rowBox.width * 0.42 - cx);
      const ty = Math.round(rowBox.top + rowBox.height / 2 - cy);
      const base = getComputedStyle(card).transform;
      const delay = T0 + index * GAP;
      animate(
        card,
        [
          { transform: base, opacity: 1, easing: OUT },
          { transform: `${base} translateY(-12px) scale(1.04)`, opacity: 1, offset: 0.2, easing: 'cubic-bezier(.34,1.2,.64,1)' },
          { transform: `translate(${tx}px,${ty}px) rotate(0deg) scale(.42)`, opacity: 1, offset: 0.78, easing: 'cubic-bezier(.4,0,1,1)' },
          { transform: `translate(${tx}px,${ty}px) rotate(0deg) scale(.3)`, opacity: 0 },
        ],
        { duration: FLY, delay },
      );
      writeCells(rows[index], delay + WRITE_AT);
      animate(
        rows[index],
        [{ backgroundColor: 'rgba(29,90,69,.13)' }, { backgroundColor: 'rgba(29,90,69,0)' }],
        { duration: 1200, delay: delay + WRITE_AT, easing: 'ease-out', fill: 'forwards' },
      );
      if (index === 0) writeCells(foot('exp'), delay + WRITE_AT + 120);
      const from = sub;
      sub += VAT[index];
      const to = sub;
      at(delay + WRITE_AT + 200, () => {
        if (id === run) count(vExp, from, to, 380, minus, id);
      });
    });
    const tEnd = T0 + 3 * GAP + WRITE_AT + WRITE;
    writeCells(foot('sales'), tEnd + 150);
    [...SALES].forEach((_, index) => {
      at(tEnd + 300 + index * 75, () => {
        if (id === run) vSales.textContent = SALES.slice(0, index + 1);
      });
    });
    writeCells(foot('total'), tEnd + 820);
    at(tEnd + 900, () => {
      if (id === run) count(vTotal, 0, TOTAL, 900, '', id);
    });
    animate(dbl, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], {
      duration: 520,
      delay: tEnd + 1760,
      easing: IO,
    });
    animate(
      pack,
      [
        { opacity: 0, transform: 'translateY(10px) scale(.97)' },
        { opacity: 1, transform: 'none' },
      ],
      { duration: 560, delay: tEnd + 2060, easing: SPRING },
    );
    at(tEnd + 2700, () => {
      if (id === run) finish();
    });
  };
  const go = () => requestAnimationFrame(play);
  Promise.race([
    document.fonts ? document.fonts.ready : Promise.resolve(),
    new Promise((resolve) => setTimeout(resolve, 1200)),
  ]).then(go);
  if (replay) replay.addEventListener('click', play);
}

function mountProduct() {
  const desk = document.querySelector('#desk');
  const steps = [...document.querySelectorAll('.pstep')];
  if (!desk || !steps.length) return;
  const wide = window.matchMedia('(min-width: 64em)');
  const motionOK = window.matchMedia('(prefers-reduced-motion: no-preference)').matches;
  let lockUntil = 0;
  const setState = (n) => {
    if (desk.dataset.state === String(n)) return;
    desk.dataset.state = String(n);
    desk.querySelectorAll('[data-s]').forEach((el) => {
      el.classList.toggle('is-on', el.dataset.s === String(n));
    });
    steps.forEach((step, index) => {
      step.classList.toggle('is-active', index === n);
      step.querySelector('.pstep__btn').setAttribute('aria-pressed', String(index === n));
    });
  };
  setState(0);
  steps.forEach((step, index) => {
    step.querySelector('.pstep__btn').addEventListener('click', () => {
      setState(index);
      lockUntil = performance.now() + 900;
      if (!wide.matches) desk.scrollIntoView({ block: 'nearest', behavior: motionOK ? 'smooth' : 'auto' });
    });
  });
  if (!('IntersectionObserver' in window)) return;
  const observer = new IntersectionObserver(
    (entries) => {
      if (!wide.matches || performance.now() < lockUntil) return;
      entries.forEach((entry) => {
        if (entry.isIntersecting) setState(Number(entry.target.dataset.step));
      });
    },
    { rootMargin: '-45% 0px -45% 0px' },
  );
  steps.forEach((step) => observer.observe(step));
}

function mountReveal() {
  const reveals = document.querySelectorAll('.reveal, .drop, .fan');
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
mountHero();
mountProduct();
mountReveal();
mountAnalytics();
track('visit');
