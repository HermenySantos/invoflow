/**
 * API client for InvoFlow backend.
 * Handles all HTTP requests with proper error handling.
 */

const API_BASE = '/api';

interface ApiError {
  message: string;
  status: number;
}

class ApiClient {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

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

    // Handle empty responses
    const contentType = response.headers.get('content-type');
    if (contentType?.includes('application/json')) {
      return response.json();
    }
    
    return response as unknown as T;
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
  }) {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.page_size) searchParams.set('page_size', params.page_size.toString());
    if (params?.status) searchParams.set('status', params.status);
    
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

  // Export
  async getExportUrl(params?: {
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
    return `${API_BASE}/export${query ? `?${query}` : ''}`;
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
export interface Document {
  id: string;
  user_id: string;
  status: 'pending' | 'processing' | 'ready' | 'needs_review' | 'failed';
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

export interface Summary {
  period: string;
  period_type: string;
  total_documents: number;
  ready_count: number;
  needs_review_count: number;
  processing_count: number;
  failed_count: number;
  total_gross: string;
  total_net: string;
  total_vat: string;
  deductible_vat: string;
  vat_on_sales: string;
  estimated_iva_payable: string;
  confidence_percent: number;
  warnings: string[];
}

export const api = new ApiClient();
