import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api } from '@/lib/api';

describe('API Client', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('request handling', () => {
    it('handles successful JSON response', async () => {
      const mockData = { documents: [], total: 0, page: 1, page_size: 20, has_more: false };
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockData),
      });

      const result = await api.getDocuments();
      expect(result).toBeDefined();
      expect(result.documents).toEqual([]);
    });

    it('handles 204 No Content response', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        headers: new Headers({ 'content-length': '0' }),
      });

      const result = await api.deleteDocument('123');
      expect(result).toBeUndefined();
    });

    it('throws error on error response', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ detail: 'Not found' }),
      });

      await expect(api.getDocument('nonexistent')).rejects.toThrow();
    });

    it('handles network errors', async () => {
      global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

      await expect(api.getDocuments()).rejects.toThrow('Network error');
    });
  });

  describe('document operations', () => {
    it('lists documents with correct URL', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ documents: [], total: 0, page: 1, page_size: 20, has_more: false }),
      });

      await api.getDocuments();
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/documents'),
        expect.any(Object)
      );
    });

    it('creates document with correct body', async () => {
      const createData = {
        storage_key: 'test/key',
        original_filename: 'test.jpg',
        mime_type: 'image/jpeg',
        file_size: 1024,
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ id: '123', ...createData }),
      });

      await api.createDocument(createData);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/documents'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(createData),
        })
      );
    });

    it('gets single document by ID', async () => {
      const mockDoc = { id: '123', vendor_name: 'Test Vendor' };
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockDoc),
      });

      const result = await api.getDocument('123');
      
      expect(result.id).toBe('123');
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/documents/123'),
        expect.any(Object)
      );
    });

    it('updates document with PATCH method', async () => {
      const updateData = { vendor_name: 'Updated Vendor' };
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ id: '123', ...updateData }),
      });

      await api.updateDocument('123', updateData);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/documents/123'),
        expect.objectContaining({
          method: 'PATCH',
        })
      );
    });
  });
});
