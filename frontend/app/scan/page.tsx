'use client';

import { useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { AppLayout } from '@/components/layout/AppLayout';
import { api } from '@/lib/api';
import { 
  Camera, 
  Upload, 
  X, 
  Check,
  Loader2,
  ImagePlus
} from 'lucide-react';
import { clsx } from 'clsx';

type UploadState = 'idle' | 'preview' | 'uploading' | 'success' | 'error';

export default function ScanPage() {
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

    // Validate file type
    if (!file.type.startsWith('image/') && file.type !== 'application/pdf') {
      setError('Please select an image or PDF file');
      return;
    }

    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      setError('File size must be less than 10MB');
      return;
    }

    setSelectedFile(file);
    setError(null);

    // Create preview for images
    if (file.type.startsWith('image/')) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
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
      
      // Navigate to receipts after short delay
      setTimeout(() => {
        router.push('/receipts');
      }, 1000);
    } catch (err) {
      console.error('Upload failed:', err);
      setError('Upload failed. Please try again.');
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
    
    // Reset file inputs
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (cameraInputRef.current) cameraInputRef.current.value = '';
  };

  const triggerCamera = () => {
    cameraInputRef.current?.click();
  };

  const triggerFileSelect = () => {
    fileInputRef.current?.click();
  };

  return (
    <AppLayout title="Scan Receipt">
      <div className="p-4">
        {/* Hidden file inputs */}
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
            {/* Camera button - primary action */}
            <button
              onClick={triggerCamera}
              className="card p-8 w-full flex flex-col items-center justify-center gap-4 hover:bg-gray-50 transition-colors border-2 border-dashed border-gray-300 hover:border-primary-400"
            >
              <div className="w-20 h-20 rounded-full bg-primary-100 flex items-center justify-center">
                <Camera className="w-10 h-10 text-primary-600" />
              </div>
              <div className="text-center">
                <p className="text-lg font-medium text-gray-900">Take Photo</p>
                <p className="text-sm text-gray-500">Use your camera to scan a receipt</p>
              </div>
            </button>

            {/* Alternative: File upload */}
            <button
              onClick={triggerFileSelect}
              className="card p-4 w-full flex items-center justify-center gap-3 hover:bg-gray-50 transition-colors"
            >
              <ImagePlus className="w-6 h-6 text-gray-500" />
              <span className="font-medium text-gray-700">
                Upload from Gallery
              </span>
            </button>

            <p className="text-center text-sm text-gray-500">
              Supported: JPG, PNG, PDF (max 10MB)
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Preview */}
            <div className="card overflow-hidden">
              {previewUrl ? (
                <img
                  src={previewUrl}
                  alt="Preview"
                  className="w-full object-contain max-h-80 bg-gray-100"
                />
              ) : selectedFile ? (
                <div className="p-8 text-center bg-gray-100">
                  <Upload className="w-12 h-12 text-gray-400 mx-auto mb-2" />
                  <p className="text-gray-600">{selectedFile.name}</p>
                  <p className="text-sm text-gray-500">
                    {(selectedFile.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              ) : null}
            </div>

            {/* Error message */}
            {error && (
              <div className="card p-3 bg-red-50 border-red-200">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}

            {/* Success message */}
            {state === 'success' && (
              <div className="card p-4 bg-green-50 border-green-200 flex items-center gap-3">
                <Check className="w-6 h-6 text-green-600" />
                <div>
                  <p className="font-medium text-green-900">Uploaded!</p>
                  <p className="text-sm text-green-700">Processing with OCR...</p>
                </div>
              </div>
            )}

            {/* Action buttons */}
            {state !== 'success' && (
              <div className="flex gap-3">
                <button
                  onClick={handleCancel}
                  disabled={state === 'uploading'}
                  className="btn-secondary btn-lg flex-1 flex items-center justify-center gap-2"
                >
                  <X className="w-5 h-5" />
                  Cancel
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
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Check className="w-5 h-5" />
                      Upload
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
