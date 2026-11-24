'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import { accountNavItem, isNavItemActive, primaryNavItems } from './navItems';

/** Same destinations as the rail. Conta is here so /settings has aria-current below 1024. */
const items = [...primaryNavItems, accountNavItem];

export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav
      className="z-50 shrink-0 border-t border-[var(--ff-border)] bg-[var(--ff-bg)] safe-area-inset-bottom print:hidden lg:hidden"
      aria-label="Navegação principal"
    >
      <ul className="m-0 mx-auto flex h-16 max-w-lg list-none items-center justify-around p-0 md:max-w-3xl md:px-8">
        {items.map(({ href, match, icon: Icon, label }) => {
          const isActive = isNavItemActive(pathname, match);
          return (
            <li key={href} className="h-full flex-1">
              <Link
                href={href}
                className={clsx(
                  'flex h-full w-full flex-col items-center justify-center transition-colors',
                  isActive ? 'text-primary-600' : 'text-gray-500 hover:text-gray-700'
                )}
                aria-current={isActive ? 'page' : undefined}
              >
                <Icon className={clsx('h-6 w-6', isActive && 'stroke-[2.5]')} aria-hidden="true" />
                <span className="mt-1 text-xs font-medium">{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
