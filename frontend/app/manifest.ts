import type { MetadataRoute } from 'next';
import { APP_DESCRIPTION, APP_NAME, BACKGROUND_COLOR, THEME_COLOR } from '@/lib/pwa';

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
      { src: '/icons/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
    ],
    shortcuts: [
      { name: 'Carregar recibo', short_name: 'Carregar', url: '/upload' },
      { name: 'Recibos', url: '/receipts' },
      { name: 'IVA', url: '/summary' },
    ],
  };
}
