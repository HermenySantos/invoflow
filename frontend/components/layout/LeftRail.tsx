'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import { accountNavItem, isNavItemActive, primaryNavItems } from './navItems';

const railItems = [...primaryNavItems, accountNavItem];

/** Full #1b4d3e ring. Same token as the header account control, plus the 2px offset. */
const focusRing =
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ff-accent)] focus-visible:ring-offset-2';

export function LeftRail() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Navegação principal"
      className="sticky top-0 hidden h-[100dvh] w-[220px] shrink-0 flex-col border-r border-[#e5e5e0] bg-white print:hidden lg:flex"
    >
      <p className="px-4 pb-3 pt-5 font-sans text-[18px] font-semibold leading-none text-[var(--ff-text)]">
        Invoflow
      </p>
      <ul className="m-0 list-none px-2">
        {railItems.map(({ href, match, icon: Icon, label }) => {
          const isActive = isNavItemActive(pathname, match);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={isActive ? 'page' : undefined}
                className={clsx(
                  'flex min-h-11 w-full items-center gap-2 px-3 text-sm',
                  focusRing,
                  isActive
                    ? 'border-l-[3px] border-l-[#1b4d3e] bg-[#1b4d3e]/[0.08] font-semibold text-[var(--ff-text)]'
                    : 'border-l-[3px] border-l-transparent font-normal text-[#5c5c5c]',
                )}
              >
                <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
                <span>{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
