'use client';

import { MouseEvent, ReactNode, RefObject, useEffect, useRef } from 'react';
import { ModalPortal } from './ModalPortal';
import { LAYERS, type Layer } from './layers';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface OpenLayer {
  ref: RefObject<HTMLElement>;
  close: () => void;
}

/* One document listener for every open layer, so Escape and Tab only ever reach the top one. */
const stack: OpenLayer[] = [];

function handleKeyDown(e: KeyboardEvent) {
  const top = stack[stack.length - 1];
  const root = top?.ref.current;
  if (!root) return;
  if (e.key === 'Escape') {
    e.preventDefault();
    top.close();
    return;
  }
  if (e.key !== 'Tab') return;
  const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
  const active = document.activeElement as HTMLElement | null;
  e.preventDefault();
  if (items.length === 0) {
    root.focus();
    return;
  }
  const at = active ? items.indexOf(active) : -1;
  const next = e.shiftKey
    ? at <= 0 ? items.length - 1 : at - 1
    : at === -1 || at === items.length - 1 ? 0 : at + 1;
  items[next].focus();
}

/** Moves focus into the open overlay, traps Tab there, closes on Escape and gives focus back to the opener. */
export function useModalLayer(ref: RefObject<HTMLElement>, onClose: () => void) {
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const entry: OpenLayer = { ref, close: () => closeRef.current() };
    stack.push(entry);
    if (stack.length === 1) document.addEventListener('keydown', handleKeyDown);

    const root = ref.current;
    const first =
      root?.querySelector<HTMLElement>('[data-autofocus]') ?? root?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? root)?.focus();

    return () => {
      stack.splice(stack.indexOf(entry), 1);
      if (stack.length === 0) document.removeEventListener('keydown', handleKeyDown);
      if (opener?.isConnected) opener.focus();
    };
  }, [ref]);
}

interface ModalLayerProps {
  layer: Layer;
  onClose: () => void;
  /** A tap on the backdrop itself, not on the sheet, closes the layer. */
  closeOnBackdrop?: boolean;
  className?: string;
  children: ReactNode;
}

/** A full-screen overlay on <body>, at its place in LAYERS, with modal keyboard and focus handling. */
export function ModalLayer({ layer, onClose, closeOnBackdrop = true, className = '', children }: ModalLayerProps) {
  const ref = useRef<HTMLDivElement>(null);
  useModalLayer(ref, onClose);
  const onBackdrop = (e: MouseEvent) => {
    if (closeOnBackdrop && e.target === e.currentTarget) onClose();
  };
  return (
    <ModalPortal>
      <div ref={ref} tabIndex={-1} className={`fixed inset-0 ${LAYERS[layer]} focus:outline-none ${className}`} onClick={onBackdrop}>
        {children}
      </div>
    </ModalPortal>
  );
}
