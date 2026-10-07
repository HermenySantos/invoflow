import type { Metadata, Viewport } from 'next';
import { IBM_Plex_Sans, Inter } from 'next/font/google';
import { ClerkProvider } from '@clerk/nextjs';
import './globals.css';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { OfflineProvider } from '@/components/providers/OfflineProvider';

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
  manifest: '/manifest.json',
  icons: {
    icon: '/favicon.svg',
    apple: '/favicon.svg',
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: 'Invoflow',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#1B4D3E',
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
    <html lang="pt" className={`${plex.variable} ${inter.variable}`}>
      <body>
        {clerkEnabled ? <ClerkProvider>{app}</ClerkProvider> : app}
      </body>
    </html>
  );
}
