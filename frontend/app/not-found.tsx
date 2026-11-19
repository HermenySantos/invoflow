import type { Metadata } from 'next';
import Link from 'next/link';
import { NotFoundActions } from '@/components/RecoveryActions';

export const metadata: Metadata = {
  title: 'Esta página não existe — Invoflow',
};

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-[var(--ff-bg)] px-4 py-10 font-sans text-[var(--ff-text)]">
      <Link
        href="/"
        className="mb-6 inline-flex min-h-11 items-center text-[20px] font-semibold text-[var(--ff-text)]"
      >
        Invoflow
      </Link>
      <div className="card w-full max-w-md p-8 text-center">
        <p
          aria-hidden="true"
          className="text-[64px] font-semibold leading-none tracking-[-0.02em] text-[var(--ff-accent)]"
        >
          404
        </p>
        <h1 className="mt-4 text-[20px] font-semibold">Esta página não existe</h1>
        <p className="mx-auto mt-2 max-w-[36ch] text-[16px] font-normal text-[var(--ff-text-muted)]">
          O endereço pode estar errado, ou a página já não está disponível.
        </p>
        <NotFoundActions />
      </div>
    </main>
  );
}
