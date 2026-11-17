'use client';

import { ReactNode } from 'react';
import { createPortal } from 'react-dom';

/** Mounts an overlay on <body>, outside #main-content, so its z-index is compared directly with BottomNav's z-50. */
export function ModalPortal({ children }: { children: ReactNode }) {
  return typeof document === 'undefined' ? null : createPortal(children, document.body);
}
