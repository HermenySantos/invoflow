'use client';

import { useState } from 'react';
import { Clock, Download, Loader2, X } from 'lucide-react';
import { AppLayout } from '@/components/layout/AppLayout';
import { useAuth } from '@/components/providers/AuthProvider';
import { SignOutConfirm } from '@/components/settings/SignOutConfirm';
import { DeleteAccountSheet } from '@/components/settings/DeleteAccountSheet';
import { RateLimitNotice } from '@/components/RateLimitNotice';
import { api } from '@/lib/api';
import { rateLimitWait, useRetryCountdown } from '@/lib/rateLimit';
import { softDisabled } from '@/lib/softDisabled';
import { rateLimitButton, rateLimitStatus, RATE_LIMIT_BUTTON_LABEL } from '@/lib/rateLimitCopy';

const EXPORT_FAILED = 'Não foi possível exportar os seus dados. Tente novamente.';

/** On unless NEXT_PUBLIC_ACCOUNT_EXPORT=0, which matches a backend with ACCOUNT_EXPORT_ENABLED=false. */
const accountExportEnabled = () => process.env.NEXT_PUBLIC_ACCOUNT_EXPORT !== '0';

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

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
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const exportWait = useRetryCountdown();
  const exportEnabled = accountExportEnabled();
  const name = user?.name?.trim();

  const exportData = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const { blob, filename } = await api.downloadAccountExport();
      saveBlob(blob, filename);
    } catch (err) {
      const wait = rateLimitWait(err);
      if (wait !== null) {
        exportWait.start(wait, rateLimitStatus(wait));
      } else {
        setExportError(EXPORT_FAILED);
      }
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-8 px-4 pt-6 md:px-0">
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

      <section aria-labelledby="data-heading">
        <h2 id="data-heading" className="sr-only">
          Dados
        </h2>
        {exportEnabled ? (
          <>
            <button
              type="button"
              {...softDisabled(exporting || exportWait.seconds !== null)}
              aria-label={exportWait.seconds !== null ? RATE_LIMIT_BUTTON_LABEL : undefined}
              onClick={exportData}
              aria-busy={exporting || undefined}
              aria-describedby="export-description"
              className="w-full btn-secondary btn-md min-h-11 gap-2"
            >
              {exportWait.seconds !== null ? (
                <>
                  <Clock className="w-4 h-4" aria-hidden="true" />
                  <span aria-hidden="true">{rateLimitButton(exportWait.seconds)}</span>
                </>
              ) : (
                <>
                  {exporting ? (
                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Download className="w-4 h-4" aria-hidden="true" />
                  )}
                  Exportar os meus dados
                </>
              )}
            </button>
            <p id="export-description" className="mt-2 text-sm text-[var(--ff-text-muted)]">
              Um ficheiro ZIP com os seus recibos, os dados de cada documento e o IVA das vendas que introduziu.
            </p>
            <RateLimitNotice message={exportWait.message} className="mt-3" />
            <p role="status" className="sr-only">
              {exporting ? 'A preparar o ficheiro…' : ''}
            </p>
          </>
        ) : (
          <>
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
          </>
        )}
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

      {exportError && (
        <div
          role="alert"
          className="fixed inset-x-4 bottom-24 z-50 mx-auto max-w-lg card flex items-start gap-3 p-4 shadow-lg border-[var(--ff-danger)] lg:bottom-6"
        >
          <p className="flex-1 text-sm text-[var(--ff-danger)]">{exportError}</p>
          <button
            type="button"
            onClick={() => setExportError(null)}
            aria-label="Fechar"
            className="-m-2 h-11 w-11 shrink-0 inline-flex items-center justify-center text-[var(--ff-text-muted)]"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      )}

      {deleteOpen && (
        <DeleteAccountSheet onClose={() => setDeleteOpen(false)} onDeleted={() => signOut('/?conta=eliminada')} />
      )}
    </div>
  );
}
