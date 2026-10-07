'use client';

/**
 * Auth provider.
 * Uses Clerk when NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is set.
 * Otherwise keeps the local demo sign-in (any email, no password).
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useUser, useClerk } from '@clerk/nextjs';
import { DEMO_AUTH_KEY, demoUserId, readDemoUser } from '@/lib/demoUser';

interface User {
  id: string;
  email: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  signIn: (email: string) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
  if (clerkEnabled) {
    return <ClerkAuthBridge>{children}</ClerkAuthBridge>;
  }
  return <MockAuthProvider>{children}</MockAuthProvider>;
}

function MockAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setUser(readDemoUser());
    setIsLoading(false);
  }, []);

  const signIn = (email: string) => {
    const demoEmail = email.trim() || 'demo@invoflow.test';
    const demoUser: User = { id: demoUserId(demoEmail), email: demoEmail };
    setUser(demoUser);
    localStorage.setItem(DEMO_AUTH_KEY, JSON.stringify(demoUser));
  };

  const signOut = () => {
    setUser(null);
    localStorage.removeItem(DEMO_AUTH_KEY);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        signIn,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

function ClerkAuthBridge({ children }: { children: ReactNode }) {
  const { user: clerkUser, isLoaded, isSignedIn } = useUser();
  const { signOut: clerkSignOut } = useClerk();

  const user: User | null = clerkUser
    ? {
        id: clerkUser.id,
        email: clerkUser.primaryEmailAddress?.emailAddress || '',
      }
    : null;

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!isSignedIn,
        isLoading: !isLoaded,
        signIn: () => {},
        signOut: () => clerkSignOut(),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
