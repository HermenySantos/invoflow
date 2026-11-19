'use client';

import { ModalLayer } from '@/components/layout/ModalLayer';

interface SignOutConfirmProps {
  onCancel: () => void;
  onConfirm: () => void;
}

export function SignOutConfirm({ onCancel, onConfirm }: SignOutConfirmProps) {
  return (
    <ModalLayer
      layer="sheet"
      onClose={onCancel}
      className="flex items-end sm:items-center justify-center p-4 pb-[calc(1rem+env(safe-area-inset-bottom,0px))] bg-black/50"
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="sign-out-title"
        aria-describedby="sign-out-body"
        className="bg-[var(--ff-surface)] rounded-t-2xl sm:rounded-2xl shadow-xl w-full max-w-sm p-6"
      >
        <h2 id="sign-out-title" className="text-lg font-semibold text-[var(--ff-text)]">
          Terminar sessão?
        </h2>
        <p id="sign-out-body" className="mt-2 mb-6 text-[var(--ff-text-muted)]">
          Vai sair desta conta neste dispositivo.
        </p>
        <div className="flex gap-3">
          <button type="button" data-autofocus onClick={onCancel} className="flex-1 btn-secondary btn-md min-h-11">
            Cancelar
          </button>
          <button type="button" onClick={onConfirm} className="flex-1 btn-accent-outline btn-md min-h-11">
            Terminar
          </button>
        </div>
      </div>
    </ModalLayer>
  );
}
