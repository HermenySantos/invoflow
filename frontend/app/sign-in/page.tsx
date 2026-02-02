'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/providers/AuthProvider';
import { Receipt } from 'lucide-react';

export default function SignInPage() {
  const [email, setEmail] = useState('');
  const router = useRouter();
  const { signIn } = useAuth();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    signIn(email || 'dev@invoflow.test');
    router.push('/summary');
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-primary-50 to-white px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary-600 mb-4">
            <Receipt className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">InvoFlow</h1>
          <p className="text-gray-600 mt-1">Receipt management made simple</p>
        </div>

        {/* Sign In Card */}
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Sign In</h2>
          
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="input"
              />
            </div>
            
            <button type="submit" className="btn-primary btn-lg w-full">
              Continue
            </button>
          </form>

          <div className="mt-4 p-3 bg-amber-50 rounded-lg border border-amber-200">
            <p className="text-sm text-amber-800">
              <strong>Demo Mode:</strong> No password needed. Just enter any email to continue.
            </p>
          </div>
        </div>

        <p className="text-center text-sm text-gray-500 mt-6">
          Simple IVA estimation for Portuguese businesses
        </p>
      </div>
    </div>
  );
}
