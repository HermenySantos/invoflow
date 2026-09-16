'use client';

import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { Camera, Check, ImagePlus, Loader2, Upload, X } from 'lucide-react';
import { clsx } from 'clsx';

type UploadState = 'idle' | 'preview' | 'uploading' | 'success' | 'error';

export function ScanReceipt() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const [state, setState] = useState<UploadState>('idle');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/') && file.type !== 'application/pdf') {
      setError('Escolha uma imagem ou PDF.');
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setError('O ficheiro tem de ter menos de 10 MB.');
      return;
    }

    setSelectedFile(file);
    setError(null);

    if (file.type.startsWith('image/')) {
      setPreviewUrl(URL.createObjectURL(file));
    } else {
      setPreviewUrl(null);
    }

    setState('preview');
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    try {
      setState('uploading');
      setError(null);
      await api.uploadFile(selectedFile);
      setState('success');
      setTimeout(() => {
        router.push('/receipts');
      }, 800);
    } catch (err) {
      console.error('Upload failed:', err);
      setError('O carregamento falhou. Tente outra vez.');
      setState('error');
    }
  };

  const handleCancel = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setPreviewUrl(null);
    setSelectedFile(null);
    setError(null);
    setState('idle');
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (cameraInputRef.current) cameraInputRef.current.value = '';
  };

  return (
    <div className="p-4">
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleFileSelect}
        className="hidden"
      />
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,application/pdf"
        onChange={handleFileSelect}
        className="hidden"
      />

      {state === 'idle' ? (
        <div className="space-y-4">
          <button
            onClick={() => cameraInputRef.current?.click()}
            className="card p-8 w-full flex flex-col items-center justify-center gap-4 hover:bg-gray-50 transition-colors border-2 border-dashed border-gray-300"
          >
            <div className="w-20 h-20 rounded-full bg-primary-100 flex items-center justify-center">
              <Camera className="w-10 h-10 text-primary-600" />
            </div>
            <div className="text-center">
              <p className="text-lg font-medium text-gray-900">Fotografar</p>
              <p className="text-sm text-gray-500">Use a câmara para um recibo</p>
            </div>
          </button>

          <button
            onClick={() => fileInputRef.current?.click()}
            className="card p-4 w-full flex items-center justify-center gap-3 hover:bg-gray-50 transition-colors"
          >
            <ImagePlus className="w-6 h-6 text-gray-500" />
            <span className="font-medium text-gray-700">Carregar PDF ou foto</span>
          </button>

          <p className="text-center text-sm text-gray-500">JPG, PNG, PDF · máximo 10 MB</p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="card overflow-hidden">
            {previewUrl ? (
              <img
                src={previewUrl}
                alt="Pré-visualização"
                className="w-full object-contain max-h-80 bg-gray-100"
              />
            ) : selectedFile ? (
              <div className="p-8 text-center bg-gray-100">
                <Upload className="w-12 h-12 text-gray-400 mx-auto mb-2" />
                <p className="text-gray-600">{selectedFile.name}</p>
                <p className="text-sm text-gray-500">{(selectedFile.size / 1024).toFixed(1)} KB</p>
              </div>
            ) : null}
          </div>

          {error && (
            <div className="card p-3 bg-red-50 border-red-200">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          {state === 'success' && (
            <div className="card p-4 bg-green-50 border-green-200 flex items-center gap-3">
              <Check className="w-6 h-6 text-green-600" />
              <div>
                <p className="font-medium text-green-900">Carregado</p>
                <p className="text-sm text-green-700">A extrair dados do documento…</p>
              </div>
            </div>
          )}

          {state !== 'success' && (
            <div className="flex gap-3">
              <button
                onClick={handleCancel}
                disabled={state === 'uploading'}
                className="btn-secondary btn-lg flex-1 flex items-center justify-center gap-2"
              >
                <X className="w-5 h-5" />
                Cancelar
              </button>
              <button
                onClick={handleUpload}
                disabled={state === 'uploading'}
                className={clsx(
                  'btn-primary btn-lg flex-1 flex items-center justify-center gap-2',
                  state === 'uploading' && 'opacity-75'
                )}
              >
                {state === 'uploading' ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    A carregar…
                  </>
                ) : (
                  <>
                    <Check className="w-5 h-5" />
                    Carregar
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
