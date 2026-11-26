import { afterEach, describe, it, expect, vi } from 'vitest';
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('@/lib/api', () => ({
  api: {
    uploadFile: vi.fn(),
  },
}));

import { ScanReceipt } from '@/components/scan/ScanReceipt';
import { api } from '@/lib/api';
import { expectEmptyRegion, expectRegionSays, getRateLimitRegion } from '../../rateLimitRegion';

const FORMAT_MESSAGE =
  'Formato não suportado. Envie um JPEG, PNG, GIF, BMP, TIFF, WEBP, HEIC ou PDF.';

function chooseFile() {
  render(<ScanReceipt />);
  const input = document.querySelector(
    'input[type="file"][accept="image/*,application/pdf"]'
  ) as HTMLInputElement;
  const file = new File([new Uint8Array([1, 2, 3])], 'nota.heic', { type: 'image/heic' });
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: 'Carregar' }));
}

describe('ScanReceipt upload errors', () => {
  it('shows the server format message instead of the generic failure', async () => {
    vi.mocked(api.uploadFile).mockRejectedValue({ message: FORMAT_MESSAGE, status: 415 });
    chooseFile();
    expect(await screen.findByText(FORMAT_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByText('O carregamento falhou. Tente outra vez.')).not.toBeInTheDocument();
  });

  it('keeps the generic message when the upload fails for another reason', async () => {
    vi.mocked(api.uploadFile).mockRejectedValue(new Error('Failed to upload file'));
    chooseFile();
    expect(await screen.findByText('O carregamento falhou. Tente outra vez.')).toBeInTheDocument();
  });
});

describe('ScanReceipt when the upload is rate limited (429)', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(api.uploadFile).mockReset();
  });

  it('keeps the file, says when to retry, counts down on the button and re-enables it at 0', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(api.uploadFile)
      .mockReset()
      .mockRejectedValueOnce({
        status: 429,
        message: 'Demasiados pedidos. Aguarde 30 s e tente novamente.',
        retryAfter: 3,
      })
      .mockResolvedValueOnce({} as never);
    render(<ScanReceipt />);
    const input = document.querySelector('input[type="file"][accept="image/*,application/pdf"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File([new Uint8Array([1, 2, 3])], 'nota.heic', { type: 'image/heic' })] } });
    // ARIA22 step 1: once a file is chosen (the only state that can upload), the region is there, empty.
    const regionBefore = getRateLimitRegion();
    expectEmptyRegion(regionBefore);
    fireEvent.click(screen.getByRole('button', { name: 'Carregar' }));

    const notice = await screen.findByRole('status');
    expect(notice).toBe(regionBefore);
    expect(notice).toHaveAttribute('aria-atomic', 'true');
    expectRegionSays(notice, 'O ficheiro continua selecionado.');
    expect(notice).toHaveTextContent(
      'O ficheiro continua selecionado. Aguarde um momento. Pode tentar de novo dentro de 3 s.',
    );
    expect(notice.textContent).not.toMatch(/Tente (novamente|outra vez)/i);
    expect(notice.className).not.toMatch(/red|danger/);
    expect(screen.queryByText('O carregamento falhou. Tente outra vez.')).not.toBeInTheDocument();
    // The file is still selected: its preview stays and no reselect is needed.
    expect(screen.getByRole('img', { name: 'Pré-visualização' })).toBeInTheDocument();

    const button = screen.getByRole('button', { name: 'Tentar de novo em 3 s' });
    expect(button).toBeDisabled();
    expect(notice).not.toContainElement(button);
    expect(button.closest('[aria-live],[role="status"],[role="alert"]')).toBeNull();

    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByRole('button', { name: 'Tentar de novo em 2 s' })).toBeDisabled();
    expect(screen.getByRole('status')).toBe(notice);
    expect(notice).toHaveTextContent('dentro de 3 s');

    act(() => vi.advanceTimersByTime(2000));
    const again = screen.getByRole('button', { name: 'Carregar' });
    expect(again).toBeEnabled();
    // The region stays mounted and empties, so nothing new is announced when the wait ends.
    expect(screen.getByRole('status')).toBe(regionBefore);
    expectEmptyRegion(regionBefore);

    fireEvent.click(again);
    await waitFor(() => expect(api.uploadFile).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.uploadFile).mock.calls[1][0]).toBe(vi.mocked(api.uploadFile).mock.calls[0][0]);
  });
});

describe('ScanReceipt on a phone', () => {
  it('opens the rear camera from "Fotografar" and the file picker from the other button', () => {
    render(<ScanReceipt />);
    const [camera, files] = Array.from(document.querySelectorAll('input[type="file"]')) as HTMLInputElement[];
    expect(camera).toHaveAttribute('capture', 'environment');
    expect(camera).toHaveAttribute('accept', 'image/*');
    // No capture here, so Android offers the gallery and PDFs from Files.
    expect(files).not.toHaveAttribute('capture');
    expect(files).toHaveAttribute('accept', 'image/*,application/pdf');

    const cameraClick = vi.spyOn(camera, 'click');
    const filesClick = vi.spyOn(files, 'click');
    fireEvent.click(screen.getByRole('button', { name: /Fotografar/ }));
    expect(cameraClick).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: /Carregar PDF ou foto/ }));
    expect(filesClick).toHaveBeenCalledTimes(1);
  });
});
describe('ScanReceipt on a short screen', () => {
  it('lays the camera tile out as a row below 500 px of height, so a phone in landscape shows all of it', () => {
    render(<ScanReceipt />);
    const tile = screen.getByRole('button', { name: /Fotografar/ });
    expect(tile).toHaveClass('flex-col', 'p-8', '[@media(max-height:500px)]:flex-row', '[@media(max-height:500px)]:p-4');
    expect(tile.firstElementChild).toHaveClass('w-20', 'h-20', '[@media(max-height:500px)]:w-12', '[@media(max-height:500px)]:h-12');
  });
});
