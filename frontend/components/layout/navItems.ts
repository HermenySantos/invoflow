import type { ComponentType } from 'react';
import { Camera, PieChart, User } from 'lucide-react';
import { ReceiptSlipIcon } from '@/components/icons/ReceiptSlipIcon';

export interface AppNavItem {
  href: string;
  match: readonly string[];
  label: string;
  icon: ComponentType<{ className?: string }>;
}

/** Bottom nav and the desktop rail share this list and the same active rule. */
export const primaryNavItems: readonly AppNavItem[] = [
  { href: '/upload', match: ['/upload', '/scan'], icon: Camera, label: 'Carregar' },
  { href: '/receipts', match: ['/receipts'], icon: ReceiptSlipIcon, label: 'Recibos' },
  { href: '/summary', match: ['/summary'], icon: PieChart, label: 'IVA' },
];

/** Sign-out lives on the Conta page. The rail links there; it does not repeat Sair. */
export const accountNavItem: AppNavItem = {
  href: '/settings',
  match: ['/settings'],
  icon: User,
  label: 'Conta',
};

export function isNavItemActive(pathname: string, match: readonly string[]): boolean {
  return match.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}
