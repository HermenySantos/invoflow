import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SignInPage from '@/app/sign-in/[[...sign-in]]/page';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { DEMO_AUTH_KEY, demoUserId } from '@/lib/demoUser';

const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams('next=/summary'),
}));

vi.mock('@clerk/nextjs', () => ({
  SignIn: () => null,
  useUser: () => ({ user: null, isLoaded: true, isSignedIn: false }),
  useClerk: () => ({ signOut: vi.fn() }),
}));

function memoryStorage(): Storage {
  const items = new Map<string, string>();
  return {
    get length() { return items.size; },
    clear: () => items.clear(),
    getItem: (key) => items.get(key) ?? null,
    key: (index) => Array.from(items.keys())[index] ?? null,
    removeItem: (key) => { items.delete(key); },
    setItem: (key, value) => { items.set(key, String(value)); },
  };
}

function renderSignIn() {
  render(
    <AuthProvider>
      <SignInPage />
    </AuthProvider>,
  );
  return screen.getByLabelText('Email');
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));
}

describe('demo sign-in validation', () => {
  beforeEach(() => {
    push.mockClear();
    vi.stubGlobal('localStorage', memoryStorage());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('is an email field the browser can autofill', () => {
    const input = renderSignIn();
    expect(input).toHaveAttribute('type', 'email');
    expect(input).toBeRequired();
    expect(input).toHaveAttribute('autocomplete', 'username');
  });

  it.each(['', '   ', 'not-an-email', 'a@b', 'a b@c.pt'])(
    'stays on sign-in with an error for %j',
    (value) => {
      const input = renderSignIn();
      fireEvent.change(input, { target: { value } });
      submit();

      expect(push).not.toHaveBeenCalled();
      expect(localStorage.getItem(DEMO_AUTH_KEY)).toBeNull();
      expect(input).toHaveAttribute('aria-invalid', 'true');
      const error = screen.getByRole('alert');
      expect(error).toHaveTextContent('Introduza um email válido.');
      expect(error.className).toContain('text-sm');
      expect(error.className).toContain('text-[var(--ff-danger)]');
      expect(input).toHaveAttribute('aria-describedby', error.id);
    },
  );

  it('clears the error once the user edits the field', () => {
    const input = renderSignIn();
    submit();
    expect(screen.getByRole('alert')).toBeInTheDocument();

    fireEvent.change(input, { target: { value: 'a' } });
    expect(screen.queryByRole('alert')).toBeNull();
    expect(input).not.toHaveAttribute('aria-invalid');
  });

  it('signs in as exactly the typed email and navigates', () => {
    const input = renderSignIn();
    fireEvent.change(input, { target: { value: '  Ana@Empresa.pt ' } });
    submit();

    expect(push).toHaveBeenCalledWith('/summary');
    const stored = JSON.parse(localStorage.getItem(DEMO_AUTH_KEY)!);
    expect(stored).toEqual({ id: demoUserId('Ana@Empresa.pt'), email: 'Ana@Empresa.pt' });
    expect(JSON.stringify(stored)).not.toContain('demo@invoflow.test');
  });
});
