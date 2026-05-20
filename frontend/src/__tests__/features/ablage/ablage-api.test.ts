import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { uploadDocument, processDocumentOCR } from '@/features/ablage/api/ablage-api';

// Mock apiClient (wird von anderen Funktionen in ablage-api benoetigt)
vi.mock('@/lib/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

describe('ablage-api - Auth Token Enforcement', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('uploadDocument sollte ohne Token mit "Nicht authentifiziert" rejecten', async () => {
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
    await expect(
      uploadDocument(file, { ocr_backend: 'deepseek' })
    ).rejects.toThrow('Nicht authentifiziert');
  });

  it('uploadDocument sollte mit Whitespace-Token rejecten', async () => {
    sessionStorage.setItem('auth_token', '   ');
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
    await expect(
      uploadDocument(file, { ocr_backend: 'deepseek' })
    ).rejects.toThrow('Nicht authentifiziert');
  });

  it('processDocumentOCR sollte ohne Token mit "Nicht authentifiziert" rejecten', async () => {
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
    await expect(processDocumentOCR(file)).rejects.toThrow('Nicht authentifiziert');
  });

  it('processDocumentOCR sollte mit Whitespace-Token rejecten', async () => {
    sessionStorage.setItem('auth_token', '  \t  ');
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
    await expect(processDocumentOCR(file)).rejects.toThrow('Nicht authentifiziert');
  });
});
