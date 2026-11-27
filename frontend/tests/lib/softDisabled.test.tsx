import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { softDisabled } from '@/lib/softDisabled';
import { expectAvailable, expectHeld } from '../softDisabled';

function Form({ busy, onClick, onSubmit }: { busy: boolean; onClick: () => void; onSubmit: () => void }) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <button {...softDisabled(busy)} onClick={onClick}>
        Guardar
      </button>
    </form>
  );
}

describe('softDisabled', () => {
  it('while unavailable keeps focus, and a click neither runs the handler nor submits the form', () => {
    const onClick = vi.fn();
    const onSubmit = vi.fn();
    const { rerender } = render(<Form busy={false} onClick={onClick} onSubmit={onSubmit} />);
    const button = screen.getByRole('button', { name: 'Guardar' });
    // Focus first, then the state change (W-15): focus must survive it.
    button.focus();
    rerender(<Form busy onClick={onClick} onSubmit={onSubmit} />);

    expectHeld(button);
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(button);
  });

  it('once available, the same button works again', () => {
    const onClick = vi.fn();
    const onSubmit = vi.fn();
    const { rerender } = render(<Form busy onClick={onClick} onSubmit={onSubmit} />);
    const button = screen.getByRole('button', { name: 'Guardar' });
    button.focus();

    rerender(<Form busy={false} onClick={onClick} onSubmit={onSubmit} />);
    expect(screen.getByRole('button', { name: 'Guardar' })).toBe(button);
    expectAvailable(button);
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});
