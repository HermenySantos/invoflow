import type { Metadata, Viewport } from 'next';
import { IBM_Plex_Sans, Inter } from 'next/font/google';
import { ClerkProvider } from '@clerk/nextjs';
import { ptPT } from '@clerk/localizations';
import './globals.css';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { OfflineProvider } from '@/components/providers/OfflineProvider';
import { APP_NAME, THEME_COLOR } from '@/lib/pwa';

const plex = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-plex',
});

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
});

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export const metadata: Metadata = {
  title: 'Invoflow — IVA dos recibos para o contabilista',
  description:
    'Carregue faturas e recibos portugueses. Obtenha uma estimativa de IVA e um pacote organizado para enviar.',
  applicationName: APP_NAME,
  icons: {
    icon: [
      { url: '/favicon.svg', type: 'image/svg+xml' },
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
    ],
    apple: '/icons/apple-touch-icon.png',
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: APP_NAME,
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  // Lets the page draw under Android's gesture bar; fixed bars pad themselves with env(safe-area-inset-*).
  viewportFit: 'cover',
  themeColor: THEME_COLOR,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const app = (
    <ErrorBoundary>
      <OfflineProvider>
        <AuthProvider>{children}</AuthProvider>
      </OfflineProvider>
    </ErrorBoundary>
  );

  return (
    <html lang="pt-PT" className={`${plex.variable} ${inter.variable}`}>
      <body>
        {clerkEnabled ? <ClerkProvider localization={ptPT}>{app}</ClerkProvider> : app}
      </body>
    </html>
  );
}
