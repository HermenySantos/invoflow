'use client';

import { AppLayout } from '@/components/layout/AppLayout';
import { ScanReceipt } from '@/components/scan/ScanReceipt';

export default function UploadPage() {
  return (
    <AppLayout title="Carregar recibo">
      <ScanReceipt />
    </AppLayout>
  );
}
