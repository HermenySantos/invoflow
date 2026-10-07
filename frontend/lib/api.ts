/**
 * API client for InvoFlow backend.
 * Handles all HTTP requests with Clerk authentication.
 */

import { readDemoUser } from './demoUser';

const API_BASE = '/api';

interface ApiError {
  message: string;
  status: number;
}

class ApiClient {
  /**
   * Get the auth token from Clerk.
   * Returns null if not authenticated (e.g., during SSR or before sign-in).
   */
  private async getAuthToken(): Promise<string | null> {
    // In browser, get token from Clerk's client-side session
    if (typeof window !== 'undefined') {
      try {
        // @clerk/nextjs exposes the session token via __clerk_session cookie
        // but the proper way is to use the useAuth hook. Since we're in a
        // non-React context, we use the global Clerk instance.
        const clerk = (window as unknown as { Clerk?: { session?: { getToken: () => Promise<string | null> } } }).Clerk;
        if (clerk?.session) {
          return await clerk.session.getToken();
        }
      } catch {
        // Fall through to null
      }
    }
    return null;
  }

  /** Clerk bearer token when signed in with Clerk; otherwise the demo user's id. */
  private async authHeaders(): Promise<Record<string, string>> {
    const token = await this.getAuthToken();
    if (token) return { Authorization: `Bearer ${token}` };
    const demoUser = typeof window !== 'undefined' ? readDemoUser() : null;
    return demoUser ? { 'X-Mock-User-Id': demoUser.id } : {};
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };

    Object.assign(headers, await this.authHeaders());

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error: ApiError = {
        message: `API Error: ${response.statusText}`,
        status: response.status,
      };
      try {
        const data = await response.json();
        error.message = data.detail || data.message || error.message;
      } catch {
        // Ignore JSON parse errors
      }
      throw error;
    }

    // Handle 204 No Content and other empty responses
    if (response.status === 204 || response.headers.get('content-length') === '0') {
      return undefined as T;
    }

    // Handle JSON responses
    const contentType = response.headers.get('content-type');
    if (contentType?.includes('application/json')) {
      return response.json();
    }
    
    return undefined as T;
  }

  // Documents
  async getUploadUrl(filename: string, contentType: string) {
    return this.request<{
      upload_url: string;
      storage_key: string;
      expires_in: number;
    }>('/documents/upload-url', {
      method: 'POST',
      body: JSON.stringify({ filename, content_type: contentType }),
    });
  }

  async createDocument(data: {
    storage_key: string;
    original_filename: string;
    mime_type: string;
    file_size?: number;
  }) {
    return this.request<Document>('/documents', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getDocuments(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    expense_category?: string;
    irs_sector?: string;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.page_size) searchParams.set('page_size', params.page_size.toString());
    if (params?.status) searchParams.set('status', params.status);
    if (params?.expense_category) searchParams.set('expense_category', params.expense_category);
    if (params?.irs_sector) searchParams.set('irs_sector', params.irs_sector);
    
    const query = searchParams.toString();
    return this.request<DocumentListResponse>(
      `/documents${query ? `?${query}` : ''}`
    );
  }

  async getDocument(id: string) {
    return this.request<Document>(`/documents/${id}`);
  }

  async updateDocument(id: string, data: Partial<Document>) {
    return this.request<Document>(`/documents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteDocument(id: string) {
    return this.request<void>(`/documents/${id}`, {
      method: 'DELETE',
    });
  }

  // Audit Trail
  async getDocumentAuditTrail(documentId: string): Promise<AuditTrailResponse> {
    return this.request<AuditTrailResponse>(`/audit/documents/${documentId}`);
  }

  // Summary
  async getSummary(params?: {
    period_type?: 'month' | 'quarter';
    year?: number;
    month?: number;
    quarter?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.period_type) searchParams.set('period_type', params.period_type);
    if (params?.year) searchParams.set('year', params.year.toString());
    if (params?.month) searchParams.set('month', params.month.toString());
    if (params?.quarter) searchParams.set('quarter', params.quarter.toString());
    
    const query = searchParams.toString();
    return this.request<Summary>(`/summary${query ? `?${query}` : ''}`);
  }

  async downloadExport(params?: {
    period_type?: 'month' | 'quarter';
    year?: number;
    month?: number;
    quarter?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.period_type) searchParams.set('period_type', params.period_type);
    if (params?.year) searchParams.set('year', params.year.toString());
    if (params?.month) searchParams.set('month', params.month.toString());
    if (params?.quarter) searchParams.set('quarter', params.quarter.toString());

    const query = searchParams.toString();
    const response = await fetch(`${API_BASE}/export${query ? `?${query}` : ''}`, {
      headers: await this.authHeaders(),
    });
    if (!response.ok) {
      throw new Error('Export failed');
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="([^"]+)"/);
    return { blob, filename: match?.[1] || 'FaturaFlow_Export.zip' };
  }

  // VAT on Sales
  async upsertVatSales(data: {
    period_type: 'month' | 'quarter';
    year: number;
    period_value: number;
    vat_amount: string;
    notes?: string;
  }) {
    return this.request<VatSalesEntry>('/vat-sales', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getVatSales(params?: {
    year?: number;
    period_type?: 'month' | 'quarter';
  }) {
    const searchParams = new URLSearchParams();
    if (params?.year) searchParams.set('year', params.year.toString());
    if (params?.period_type) searchParams.set('period_type', params.period_type);

    const query = searchParams.toString();
    return this.request<{ entries: VatSalesEntry[]; total: number }>(
      `/vat-sales${query ? `?${query}` : ''}`
    );
  }

  // File upload helper
  async uploadFile(file: File): Promise<Document> {
    // Step 1: Get presigned upload URL
    const { upload_url, storage_key } = await this.getUploadUrl(
      file.name,
      file.type
    );

    // Step 2: Upload file to storage (or mock endpoint)
    const uploadResponse = await fetch(upload_url, {
      method: 'PUT',
      body: file,
      headers: {
        'Content-Type': file.type,
      },
    });

    if (!uploadResponse.ok) {
      throw new Error('Failed to upload file');
    }

    // Step 3: Create document record (triggers OCR)
    return this.createDocument({
      storage_key,
      original_filename: file.name,
      mime_type: file.type,
      file_size: file.size,
    });
  }
}

// Types
export interface ValidationWarning {
  code: string;
  message: string;
  severity: 'error' | 'warning' | 'info';
  field: string | null;
}

export interface AuditEntry {
  id: string;
  entity_type: string;
  entity_id: string;
  user_id: string;
  action: string;
  source: string;
  changes_json: string | null;
  created_at: string;
}

export interface AuditTrailResponse {
  entity_type: string;
  entity_id: string;
  entries: AuditEntry[];
  total: number;
}

export interface FieldConfidence {
  vendor_name?: number | null;
  vendor_nif?: number | null;
  invoice_number?: number | null;
  document_date?: number | null;
  net_amount?: number | null;
  vat_amount?: number | null;
  gross_amount?: number | null;
  vat_rate?: number | null;
}

export interface Document {
  id: string;
  user_id: string;
  status: 'pending' | 'processing' | 'ready' | 'needs_review' | 'accountant_review' | 'failed';
  storage_key: string;
  original_filename: string;
  mime_type: string;
  file_size: number | null;
  vendor_name: string | null;
  vendor_nif: string | null;
  invoice_number: string | null;
  document_date: string | null;
  net_amount: string | null;
  vat_amount: string | null;
  gross_amount: string | null;
  vat_rate: string | null;
  ocr_confidence: string | null;
  field_confidence: FieldConfidence | null;
  validation_warnings: ValidationWarning[];
  review_notes: string | null;
  expense_category: string | null;
  irs_sector: string | null;
  period_tag: string;
  quarter_tag: string;
  file_url: string | null;
  thumbnail_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  documents: Document[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface CategoryBreakdown {
  category: string;
  label: string;
  count: number;
  total: string;
  vat_total?: string;
  deductible_vat?: string;
  deductible_pct?: number;
}

export interface Summary {
  period: string;
  period_type: string;
  year: number;
  period_value: number;
  total_documents: number;
  ready_count: number;
  needs_review_count: number;
  processing_count: number;
  failed_count: number;
  total_gross: string;
  total_net: string;
  total_vat: string;
  deductible_vat: string;
  /** null until the user enters VAT on sales for the period */
  vat_on_sales: string | null;
  /** null while vat_on_sales is null */
  estimated_iva_payable: string | null;
  expense_breakdown: CategoryBreakdown[];
  irs_breakdown: CategoryBreakdown[];
  confidence_percent: number;
  warnings: string[];
}

export interface VatSalesEntry {
  id?: string;
  period_type: 'month' | 'quarter';
  year: number;
  period_value: number;
  vat_amount: string;
  notes?: string;
  created_at?: string;
  updated_at?: string;
}

export const api = new ApiClient();
