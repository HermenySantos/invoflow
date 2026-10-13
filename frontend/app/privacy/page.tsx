import type { Metadata } from 'next';
import { PrivacyPage } from './PrivacyPage';

export const metadata: Metadata = {
  title: 'Privacidade — Invoflow',
  description:
    'Aviso de privacidade do Invoflow: dados de faturas e NIFs, finalidades, conservação, subcontratantes na UE e direitos.',
};

export default function Page() {
  return <PrivacyPage />;
}
