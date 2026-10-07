'use client';

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { SignIn } from "@clerk/nextjs";
import { useAuth } from '@/components/providers/AuthProvider';

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

function SignInForm() {
  const [email, setEmail] = useState('');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { signIn } = useAuth();
  const next = searchParams.get('next') || '/upload';

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    signIn(email || 'demo@faturaflow.test');
    router.push(next.startsWith('/') ? next : '/upload');
  };

  return (
    <div className="landing min-h-screen flex flex-col items-center justify-center px-4">
      <div className="w-full" style={{ maxWidth: 400 }}>
        <p className="mb-8">
          <Link href="/">← FaturaFlow</Link>
        </p>
        <h1 className="text-2xl font-semibold">Entrar</h1>
        <p className="mt-2 text-[var(--ff-text-muted)]">
          Modo de demonstração: não é pedida palavra-passe. Introduza qualquer email.
        </p>

        <form onSubmit={handleSubmit} noValidate className="mt-6 space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm mb-1">
              Email
            </label>
            <input
              id="email"
              type="text"
              inputMode="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="voce@empresa.pt"
              className="input"
            />
          </div>
          <button type="submit" className="landing-btn landing-btn-primary w-full">
            Continuar
          </button>
        </form>
      </div>
    </div>
  );
}

export default function SignInPage() {
  if (clerkEnabled) {
    return (
      <div className="landing min-h-screen flex items-center justify-center px-4">
        <SignIn fallbackRedirectUrl="/upload" signUpUrl="/sign-up" />
      </div>
    );
  }

  return (
    <Suspense fallback={<div className="landing min-h-screen" />}>
      <SignInForm />
    </Suspense>
  );
}
