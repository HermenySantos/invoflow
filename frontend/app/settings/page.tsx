'use client';

import { useState } from 'react';
import { Download } from 'lucide-react';
import { AppLayout } from '@/components/layout/AppLayout';
import { useAuth } from '@/components/providers/AuthProvider';
import { SignOutConfirm } from '@/components/settings/SignOutConfirm';
import { DeleteAccountSheet } from '@/components/settings/DeleteAccountSheet';

export default function SettingsPage() {
  return (
    <AppLayout eyebrow="Conta" title="Definições">
      <SettingsContent />
    </AppLayout>
  );
}

function SettingsContent() {
  const { user, signOut } = useAuth();
  const [confirmSignOut, setConfirmSignOut] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const name = user?.name?.trim();

  return (
    <div className="max-w-lg mx-auto px-4 pt-6 space-y-8">
      <section aria-labelledby="account-heading">
        <h2 id="account-heading" className="sr-only">
          Conta
        </h2>
        <dl className="card divide-y divide-[var(--ff-border)]">
          {name && (
            <div className="px-4 py-3">
              <dt className="text-sm text-[var(--ff-text-muted)]">Nome</dt>
              <dd className="mt-0.5 text-[var(--ff-text)]">{name}</dd>
            </div>
          )}
          <div className="px-4 py-3">
            <dt className="text-sm text-[var(--ff-text-muted)]">Email</dt>
            <dd className="mt-0.5 text-[var(--ff-text)] break-all">{user?.email}</dd>
          </div>
        </dl>

        <button
          type="button"
          onClick={() => setConfirmSignOut(true)}
          className="mt-4 w-full btn-secondary btn-md min-h-11"
        >
          Terminar sessão
        </button>
      </section>

      {/* There is no whole-account export API: /api/export only builds one period's accountant pack. */}
      <section aria-labelledby="data-heading">
        <h2 id="data-heading" className="sr-only">
          Dados
        </h2>
        <button
          type="button"
          disabled
          aria-describedby="export-unavailable"
          className="w-full btn-secondary btn-md min-h-11 gap-2"
        >
          <Download className="w-4 h-4" aria-hidden="true" />
          Exportar os meus dados
        </button>
        <p id="export-unavailable" className="mt-2 text-sm text-[var(--ff-text-muted)]">
          Disponível em breve
        </p>
      </section>

      <section aria-labelledby="danger-heading" className="border-t border-[var(--ff-border)] pt-6">
        <h2 id="danger-heading" className="text-sm font-semibold text-[var(--ff-danger)]">
          Zona de perigo
        </h2>
        <button
          type="button"
          onClick={() => setDeleteOpen(true)}
          className="mt-3 btn-ghost-danger btn-md min-h-11 -ml-4"
        >
          Eliminar conta
        </button>
      </section>

      {confirmSignOut && (
        <SignOutConfirm onCancel={() => setConfirmSignOut(false)} onConfirm={() => signOut('/')} />
      )}

      {deleteOpen && (
        <DeleteAccountSheet onClose={() => setDeleteOpen(false)} onDeleted={() => signOut('/?conta=eliminada')} />
      )}
    </div>
  );
}
