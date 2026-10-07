'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Camera, Receipt, PieChart } from 'lucide-react';
import { clsx } from 'clsx';

const navItems = [
  { href: '/upload', match: ['/upload', '/scan'], icon: Camera, label: 'Carregar' },
  { href: '/receipts', match: ['/receipts'], icon: Receipt, label: 'Recibos' },
  { href: '/summary', match: ['/summary'], icon: PieChart, label: 'IVA' },
];

export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 bg-[var(--ff-bg)] border-t border-[var(--ff-border)] safe-area-inset-bottom z-50"
      aria-label="Navegação principal"
    >
      <ul className="flex items-center justify-around h-16 max-w-lg mx-auto list-none m-0 p-0">
        {navItems.map(({ href, match, icon: Icon, label }) => {
          const isActive = match.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
          return (
            <li key={href} className="flex-1 h-full">
              <Link
                href={href}
                className={clsx(
                  'flex flex-col items-center justify-center w-full h-full transition-colors',
                  isActive ? 'text-primary-600' : 'text-gray-500 hover:text-gray-700'
                )}
                aria-current={isActive ? 'page' : undefined}
              >
                <Icon className={clsx('w-6 h-6', isActive && 'stroke-[2.5]')} aria-hidden="true" />
                <span className="text-xs mt-1 font-medium">{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
