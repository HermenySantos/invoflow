'use client';

/**
 * Auth provider.
 * Uses Clerk when NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is set.
 * Otherwise keeps the local demo sign-in (any email, no password).
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useUser, useClerk } from '@clerk/nextjs';

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

const MOCK_AUTH_KEY = 'invoflow_mock_auth';

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
    const stored = localStorage.getItem(MOCK_AUTH_KEY);
    if (stored) {
      try {
        setUser(JSON.parse(stored));
      } catch {
        localStorage.removeItem(MOCK_AUTH_KEY);
      }
    }
    setIsLoading(false);
  }, []);

  const signIn = (email: string) => {
    const mockUser: User = {
      id: 'mock-user-001',
      email: email || 'dev@invoflow.test',
    };
    setUser(mockUser);
    localStorage.setItem(MOCK_AUTH_KEY, JSON.stringify(mockUser));
  };

  const signOut = () => {
    setUser(null);
    localStorage.removeItem(MOCK_AUTH_KEY);
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
