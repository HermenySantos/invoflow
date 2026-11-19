'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { ModalLayer } from '@/components/layout/ModalLayer';

export const DELETE_CONFIRM_WORD = 'ELIMINAR';

/** Exact, case-sensitive match: no trimming, so a trailing space does not confirm. */
export const isDeleteConfirmed = (typed: string) => typed === DELETE_CONFIRM_WORD;

interface DeleteAccountSheetProps {
  onClose: () => void;
  /** Calls the delete-account API. There is none yet, so the flow stops at step 1 until one is passed. */
  onDelete?: () => Promise<void>;
  onDeleted: () => void;
}

export function DeleteAccountSheet({ onClose, onDelete, onDeleted }: DeleteAccountSheetProps) {
  const enabled = Boolean(onDelete) && process.env.NEXT_PUBLIC_ACCOUNT_DELETE === '1';
  const [step, setStep] = useState<1 | 2>(1);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    if (!busy) onClose();
  };

  const confirm = async () => {
    if (!onDelete || !isDeleteConfirmed(typed)) return;
    setBusy(true);
    setError(null);
    try {
      await onDelete();
      onDeleted();
    } catch {
      setError('Não foi possível eliminar a conta. Tente novamente.');
      setBusy(false);
    }
  };

  return (
    <ModalLayer
      layer="sheet"
      onClose={close}
      className="flex items-end sm:items-center justify-center p-4 pb-[calc(1rem+env(safe-area-inset-bottom,0px))] bg-black/50"
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-account-title"
        aria-describedby={step === 1 ? 'delete-account-body' : undefined}
        className="bg-[var(--ff-surface)] rounded-t-2xl sm:rounded-2xl shadow-xl w-full max-w-sm p-6"
      >
        <h2 id="delete-account-title" className="text-lg font-semibold text-[var(--ff-text)]">
          Eliminar a conta?
        </h2>

        {step === 1 ? (
          <>
            {/* Placeholder until the retention copy is confirmed. Must not become a legal or retention claim here. */}
            <p
              id="delete-account-body"
              className="mt-3 rounded-[var(--ff-radius)] border border-dashed border-[var(--ff-border)] p-3 text-sm text-[var(--ff-text-muted)]"
            >
              [O que acontece aos recibos após eliminar a conta — a confirmar]
            </p>
            {!enabled && (
              <p id="delete-account-unavailable" className="mt-3 text-sm text-[var(--ff-text-muted)]">
                A eliminação de conta ainda não está disponível.
              </p>
            )}
            <div className="mt-6 flex gap-3">
              <button type="button" data-autofocus onClick={close} className="flex-1 btn-secondary btn-md min-h-11">
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => setStep(2)}
                disabled={!enabled}
                aria-describedby={enabled ? undefined : 'delete-account-unavailable'}
                className="flex-1 btn-secondary btn-md min-h-11"
              >
                Continuar
              </button>
            </div>
          </>
        ) : (
          <form
            className="mt-4"
            onSubmit={(e) => {
              e.preventDefault();
              void confirm();
            }}
          >
            <label htmlFor="delete-account-confirm" className="block text-sm text-[var(--ff-text)] mb-1">
              Escreva ELIMINAR para confirmar
            </label>
            <input
              id="delete-account-confirm"
              type="text"
              data-autofocus
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              disabled={busy}
              className="input"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'delete-account-error' : undefined}
            />
            {error && (
              <p id="delete-account-error" role="alert" className="mt-2 text-sm text-[var(--ff-danger)]">
                {error}
              </p>
            )}
            <div className="mt-6 flex gap-3">
              <button type="button" onClick={close} disabled={busy} className="flex-1 btn-secondary btn-md min-h-11">
                Cancelar
              </button>
              <button
                type="submit"
                disabled={!isDeleteConfirmed(typed) || busy}
                aria-busy={busy || undefined}
                className="flex-1 btn-danger btn-md min-h-11 gap-2"
              >
                {busy && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
                Eliminar conta
              </button>
            </div>
          </form>
        )}
      </div>
    </ModalLayer>
  );
}
