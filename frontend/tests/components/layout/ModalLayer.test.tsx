import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useEffect, useRef, useState } from 'react';
import { ModalLayer } from '@/components/layout/ModalLayer';
import { LAYERS } from '@/components/layout/layers';

function Sheet({ onClose = vi.fn() }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  const close = () => {
    onClose();
    setOpen(false);
  };
  return (
    <>
      <button onClick={() => setOpen(true)}>Abrir</button>
      {open && (
        <ModalLayer layer="sheet" onClose={close} className="bg-black/50">
          <div role="dialog" aria-label="Folha">
            <button>Primeiro</button>
            <button>Meio</button>
            <button>Último</button>
          </div>
        </ModalLayer>
      )}
    </>
  );
}

function openSheet(onClose = vi.fn()) {
  render(<Sheet onClose={onClose} />);
  const opener = screen.getByRole('button', { name: 'Abrir' });
  opener.focus();
  fireEvent.click(opener);
  return { opener, onClose };
}

const tab = (shiftKey = false) => fireEvent.keyDown(document.activeElement!, { key: 'Tab', shiftKey });

describe('ModalLayer', () => {
  it('moves focus into the sheet on open', () => {
    openSheet();
    expect(screen.getByRole('button', { name: 'Primeiro' })).toHaveFocus();
  });

  it('traps Tab and Shift+Tab inside the sheet', () => {
    openSheet();
    tab();
    expect(screen.getByRole('button', { name: 'Meio' })).toHaveFocus();
    tab();
    expect(screen.getByRole('button', { name: 'Último' })).toHaveFocus();
    tab();
    expect(screen.getByRole('button', { name: 'Primeiro' })).toHaveFocus();
    tab(true);
    expect(screen.getByRole('button', { name: 'Último' })).toHaveFocus();
  });

  it('pulls focus back in when it has escaped the sheet', () => {
    const { opener } = openSheet();
    opener.focus();
    tab();
    expect(screen.getByRole('button', { name: 'Primeiro' })).toHaveFocus();
  });

  it('closes on Escape and restores focus to the opener', () => {
    const { opener, onClose } = openSheet();
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('closes on a backdrop tap but not on a tap inside the sheet', () => {
    const { opener, onClose } = openSheet();
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('dialog').parentElement!);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(opener).toHaveFocus();
  });

  it('mounts on <body> at its LAYERS z-index', () => {
    const { container } = render(
      <ModalLayer layer="viewer" onClose={() => {}}>
        <button>x</button>
      </ModalLayer>,
    );
    const overlay = screen.getByRole('button').parentElement!;
    expect(overlay.parentElement).toBe(document.body);
    expect(container.contains(overlay)).toBe(false);
    expect(overlay).toHaveClass(LAYERS.viewer);
  });

  it('orders the viewer above the sheets', () => {
    const z = (cls: string) => Number(cls.match(/\d+/)![0]);
    expect(z(LAYERS.viewer)).toBeGreaterThan(z(LAYERS.sheet));
  });

  it('closes only the top layer on Escape', () => {
    const closeSheet = vi.fn();
    const closeViewer = vi.fn();
    render(
      <>
        <ModalLayer layer="sheet" onClose={closeSheet}>
          <button>Folha</button>
        </ModalLayer>
        <ModalLayer layer="viewer" onClose={closeViewer}>
          <button>Visor</button>
        </ModalLayer>
      </>,
    );
    expect(screen.getByRole('button', { name: 'Visor' })).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    expect(closeViewer).toHaveBeenCalledTimes(1);
    expect(closeSheet).not.toHaveBeenCalled();
  });

  it('marks the rest of <body> inert and aria-hidden while open, and restores it on close', () => {
    const outside = document.createElement('div');
    outside.setAttribute('aria-hidden', 'false');
    document.body.appendChild(outside);
    const { opener } = openSheet();
    const page = opener.closest('body > *')!;
    const overlay = screen.getByRole('dialog').parentElement!;

    for (const el of [page, outside]) {
      expect(el).toHaveAttribute('inert');
      expect(el).toHaveAttribute('aria-hidden', 'true');
    }
    expect(overlay).not.toHaveAttribute('inert');
    expect(overlay).not.toHaveAttribute('aria-hidden');

    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    expect(page).not.toHaveAttribute('inert');
    expect(page).not.toHaveAttribute('aria-hidden');
    expect(outside).not.toHaveAttribute('inert');
    expect(outside).toHaveAttribute('aria-hidden', 'false');
    outside.remove();
  });

  it('closes by z-order on Escape when the sheet mounts after the viewer', () => {
    function Both() {
      const [viewer, setViewer] = useState(true);
      const [sheet, setSheet] = useState(false);
      useEffect(() => setSheet(true), []);
      return (
        <>
          {viewer && (
            <ModalLayer layer="viewer" onClose={() => setViewer(false)}>
              <button>Visor</button>
            </ModalLayer>
          )}
          {sheet && (
            <ModalLayer layer="sheet" onClose={() => setSheet(false)}>
              <button>Folha</button>
            </ModalLayer>
          )}
        </>
      );
    }
    render(<Both />);
    const viewer = screen.getByRole('button', { name: 'Visor' });
    const sheetOverlay = screen.getByText('Folha').parentElement!;
    expect(viewer).toHaveFocus();
    expect(sheetOverlay).toHaveAttribute('inert');
    expect(viewer.parentElement).not.toHaveAttribute('inert');

    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    expect(screen.queryByText('Visor')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Folha' })).toBeInTheDocument();
    expect(sheetOverlay).not.toHaveAttribute('inert');

    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    expect(screen.queryByText('Folha')).not.toBeInTheDocument();
  });

  it('returns focus to returnFocusRef when the opener has left the document', () => {
    function Swap() {
      const [open, setOpen] = useState(false);
      const back = useRef<HTMLButtonElement>(null);
      return open ? (
        <ModalLayer layer="viewer" onClose={() => setOpen(false)} returnFocusRef={back}>
          <button>Visor</button>
        </ModalLayer>
      ) : (
        <button ref={back} onClick={() => setOpen(true)}>Abrir</button>
      );
    }
    render(<Swap />);
    const first = screen.getByRole('button', { name: 'Abrir' });
    first.focus();
    fireEvent.click(first);
    expect(first.isConnected).toBe(false);
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    expect(screen.getByRole('button', { name: 'Abrir' })).toHaveFocus();
  });
});
