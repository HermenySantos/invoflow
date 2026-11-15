import type { MetadataRoute } from 'next';
import { APP_DESCRIPTION, APP_NAME, BACKGROUND_COLOR, THEME_COLOR } from '@/lib/pwa';

const SHORTCUT_ICON = { src: '/icons/icon-96.png', sizes: '96x96', type: 'image/png' };

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/',
    name: APP_NAME,
    short_name: APP_NAME,
    description: APP_DESCRIPTION,
    lang: 'pt-PT',
    dir: 'ltr',
    start_url: '/upload',
    scope: '/',
    display: 'standalone',
    orientation: 'portrait',
    background_color: BACKGROUND_COLOR,
    theme_color: THEME_COLOR,
    categories: ['finance', 'business', 'productivity'],
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-maskable-192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
      { src: '/icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
    shortcuts: [
      { name: 'Carregar recibo', short_name: 'Carregar', url: '/upload', icons: [SHORTCUT_ICON] },
      { name: 'Recibos', url: '/receipts', icons: [SHORTCUT_ICON] },
      { name: 'IVA', url: '/summary', icons: [SHORTCUT_ICON] },
    ],
  };
}
