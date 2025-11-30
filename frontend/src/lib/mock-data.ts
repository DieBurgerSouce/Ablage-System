import type { Document } from '@/features/documents/types';

export const mockDocuments: Document[] = Array.from({ length: 20 }).map((_, i) => ({
    id: `doc-${i + 1}`,
    name: `Invoice_${2024001 + i}.pdf`,
    createdAt: new Date(Date.now() - i * 86400000).toISOString(),
    mimeType: 'application/pdf',
    ocrStatus: i % 5 === 0 ? 'failed' : i % 3 === 0 ? 'processing' : 'completed',
    ocrConfidence: i % 5 === 0 ? 0 : 0.85 + (Math.random() * 0.14),
}));
