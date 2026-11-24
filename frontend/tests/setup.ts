import '@testing-library/jest-dom';
import { configure } from '@testing-library/react';
import { vi } from 'vitest';
import { registerUseParamsMock } from './navigationState';

// GitHub's runner is busy enough that a findBy/waitFor can miss a render that
// lands just after the 1s default, and an axe scan can pass 5s.
configure({ asyncUtilTimeout: 5000 });

const { useParamsMock } = vi.hoisted(() => ({
  useParamsMock: vi.fn(() => ({ id: 'doc-v6' })),
}));

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => '/test',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => useParamsMock(),
}));

registerUseParamsMock(useParamsMock);

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock URL.createObjectURL
global.URL.createObjectURL = vi.fn(() => 'mock-url');
global.URL.revokeObjectURL = vi.fn();

// Mock fetch
global.fetch = vi.fn();
