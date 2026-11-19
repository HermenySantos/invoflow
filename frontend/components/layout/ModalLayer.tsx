'use client';

import { MouseEvent, ReactNode, RefObject, useEffect, useRef } from 'react';
import { ModalPortal } from './ModalPortal';
import { LAYERS, type Layer } from './layers';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface OpenLayer {
  ref: RefObject<HTMLElement>;
  z: number;
  close: () => void;
}

/* One document listener for every open layer, so Escape and Tab only ever reach the top one.
   Sorted by z-index, then by mount order, so the last entry is the layer drawn on top. */
const stack: OpenLayer[] = [];

const zIndex = (layer: Layer) => Number(LAYERS[layer].match(/\d+/)![0]);

function push(entry: OpenLayer) {
  const at = stack.findIndex((open) => open.z > entry.z);
  stack.splice(at === -1 ? stack.length : at, 0, entry);
}

/* Background elements made inert by syncBackground, with the attributes they had before. */
const hidden = new Map<Element, { inert: boolean; ariaHidden: string | null }>();

/** Leaves only the top layer reachable: every other child of <body> is inert and aria-hidden. */
function syncBackground() {
  const top = stack[stack.length - 1]?.ref.current ?? null;
  hidden.forEach((prev, el) => {
    if (top && el !== top && el.isConnected) return;
    if (!prev.inert) el.removeAttribute('inert');
    if (prev.ariaHidden === null) el.removeAttribute('aria-hidden');
    else el.setAttribute('aria-hidden', prev.ariaHidden);
    hidden.delete(el);
  });
  if (!top) return;
  for (const el of Array.from(document.body.children)) {
    if (el === top || hidden.has(el)) continue;
    hidden.set(el, { inert: el.hasAttribute('inert'), ariaHidden: el.getAttribute('aria-hidden') });
    el.setAttribute('inert', '');
    el.setAttribute('aria-hidden', 'true');
  }
}

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

interface ModalLayerOptions {
  layer?: Layer;
  /** Gets focus on close when the element that opened the layer is no longer in the document. */
  returnFocusRef?: RefObject<HTMLElement>;
}

/** Moves focus into the open overlay, traps Tab there, closes on Escape and gives focus back to the opener. */
export function useModalLayer(
  ref: RefObject<HTMLElement>,
  onClose: () => void,
  { layer = 'sheet', returnFocusRef }: ModalLayerOptions = {},
) {
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const entry: OpenLayer = { ref, z: zIndex(layer), close: () => closeRef.current() };
    push(entry);
    if (stack.length === 1) document.addEventListener('keydown', handleKeyDown);
    syncBackground();

    const root = ref.current;
    if (stack[stack.length - 1] === entry) {
      const first =
        root?.querySelector<HTMLElement>('[data-autofocus]') ?? root?.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? root)?.focus();
    }

    return () => {
      stack.splice(stack.indexOf(entry), 1);
      if (stack.length === 0) document.removeEventListener('keydown', handleKeyDown);
      syncBackground();
      const target = opener?.isConnected && opener !== document.body ? opener : returnFocusRef?.current;
      target?.focus();
    };
  }, [ref, layer, returnFocusRef]);
}

interface ModalLayerProps extends Pick<ModalLayerOptions, 'returnFocusRef'> {
  layer: Layer;
  onClose: () => void;
  /** A tap on the backdrop itself, not on the sheet, closes the layer. */
  closeOnBackdrop?: boolean;
  className?: string;
  children: ReactNode;
}

/** A full-screen overlay on <body>, at its place in LAYERS, with modal keyboard and focus handling. */
export function ModalLayer({
  layer,
  onClose,
  returnFocusRef,
  closeOnBackdrop = true,
  className = '',
  children,
}: ModalLayerProps) {
  const ref = useRef<HTMLDivElement>(null);
  useModalLayer(ref, onClose, { layer, returnFocusRef });
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
