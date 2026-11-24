'use client';

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { SignIn } from "@clerk/nextjs";
import { useAuth } from '@/components/providers/AuthProvider';
import { safeNextPath } from '@/lib/safeNext';

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const INVALID_EMAIL_MESSAGE = 'Introduza um email válido.';

function SignInForm() {
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const searchParams = useSearchParams();
  const { signIn } = useAuth();
  const next = safeNextPath(searchParams.get('next'));

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const typed = email.trim();
    if (!EMAIL_PATTERN.test(typed)) {
      setError(INVALID_EMAIL_MESSAGE);
      return;
    }
    signIn(typed);
    router.push(next);
  };

  return (
    <div className="landing min-h-screen flex flex-col items-center justify-center px-4">
      <div className="w-full" style={{ maxWidth: 400 }}>
        <p className="mb-6">
          <Link href="/" className="inline-flex min-h-11 items-center">← Invoflow</Link>
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
              type="email"
              required
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              enterKeyHint="go"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (error) setError(null);
              }}
              placeholder="voce@empresa.pt"
              className="input"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'email-error' : undefined}
            />
            {error && (
              <p id="email-error" role="alert" className="mt-1 text-sm text-[var(--ff-danger)]">
                {error}
              </p>
            )}
          </div>
          <button type="submit" className="landing-btn landing-btn-primary w-full">
            Continuar
          </button>
        </form>
      </div>
    </div>
  );
}

/** Clerk honours its own ?redirect_url= (set by the middleware); ?next= (set by AppLayout) is the fallback. */
function ClerkSignIn() {
  const searchParams = useSearchParams();
  return (
    <div className="landing min-h-screen flex items-center justify-center px-4">
      <SignIn fallbackRedirectUrl={safeNextPath(searchParams.get('next'))} signUpUrl="/sign-up" />
    </div>
  );
}

export default function SignInPage() {
  if (clerkEnabled) {
    return (
      <Suspense fallback={<div className="landing min-h-screen" />}>
        <ClerkSignIn />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<div className="landing min-h-screen" />}>
      <SignInForm />
    </Suspense>
  );
}
