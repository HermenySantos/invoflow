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
