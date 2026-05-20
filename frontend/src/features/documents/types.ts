export interface Document {
    id: string;
    name: string;
    createdAt: string;
    mimeType: string;
    thumbnail?: string;
    ocrStatus: 'pending' | 'processing' | 'completed' | 'failed';
    ocrConfidence?: number;
    detectedLanguage?: string;
    languageConfidence?: number;
}
