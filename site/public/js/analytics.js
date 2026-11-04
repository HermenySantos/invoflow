import { CONFIG } from './config.js';

export const EVENTS = ['visit', 'cta_click', 'form_submit'];

export function track(name) {
  if (!EVENTS.includes(name)) return;
  if (!CONFIG.ANALYTICS) return;
  document.dispatchEvent(new CustomEvent('invoflow-analytics', { detail: { name } }));
  if (CONFIG.ANALYTICS === 'plausible' && typeof window.plausible === 'function') {
    window.plausible(name);
  }
}

export function mountAnalytics() {
  if (CONFIG.ANALYTICS === 'plausible' && CONFIG.PLAUSIBLE_DOMAIN) {
    const script = document.createElement('script');
    script.defer = true;
    script.dataset.domain = CONFIG.PLAUSIBLE_DOMAIN;
    script.src = 'https://plausible.io/js/script.js';
    document.head.appendChild(script);
  }
  mountPixel();
}

function mountPixel() {
  const id = CONFIG.META_PIXEL_ID;
  if (!id) return;
  const stub = document.createElement('script');
  stub.src = '/js/pixel-stub.js';
  stub.onload = () => {
    const script = document.createElement('script');
    script.async = true;
    script.src = 'https://connect.facebook.net/en_US/fbevents.js';
    script.onload = () => {
      if (typeof window.fbq === 'function') {
        window.fbq('init', id);
        window.fbq('track', 'PageView');
      }
    };
    document.head.appendChild(script);
  };
  document.head.appendChild(stub);
}
