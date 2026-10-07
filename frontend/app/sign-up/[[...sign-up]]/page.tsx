import { redirect } from 'next/navigation';
import Link from 'next/link';
import { SignUp } from '@clerk/nextjs';

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export default function SignUpPage() {
  if (!clerkEnabled) {
    redirect('/sign-in');
  }

  return (
    <div className="landing min-h-screen flex flex-col items-center justify-center px-4">
      <div className="w-full" style={{ maxWidth: 400 }}>
        <p className="mb-8">
          <Link href="/">← FaturaFlow</Link>
        </p>
        <h1 className="text-2xl font-semibold">Criar conta</h1>
        <p className="mt-2 mb-6 text-[var(--ff-text-muted)]">
          Estimativa simples do IVA para empresas em Portugal.
        </p>
        <SignUp fallbackRedirectUrl="/upload" signInUrl="/sign-in" />
      </div>
    </div>
  );
}
