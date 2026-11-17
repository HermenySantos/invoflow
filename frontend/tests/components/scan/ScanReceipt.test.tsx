import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@/lib/api', () => ({
  api: {
    uploadFile: vi.fn(),
  },
}));

import { ScanReceipt } from '@/components/scan/ScanReceipt';
import { api } from '@/lib/api';

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
