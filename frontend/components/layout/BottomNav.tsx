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
    <nav className="fixed bottom-0 left-0 right-0 bg-[var(--ff-bg)] border-t border-[var(--ff-border)] safe-area-inset-bottom z-50">
      <div className="flex items-center justify-around h-16 max-w-lg mx-auto">
        {navItems.map(({ href, match, icon: Icon, label }) => {
          const isActive = match.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                'flex flex-col items-center justify-center w-full h-full transition-colors',
                isActive ? 'text-primary-600' : 'text-gray-500 hover:text-gray-700'
              )}
            >
              <Icon className={clsx('w-6 h-6', isActive && 'stroke-[2.5]')} />
              <span className="text-xs mt-1 font-medium">{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
