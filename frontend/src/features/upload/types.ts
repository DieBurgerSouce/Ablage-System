export interface Tune {
    id: string;
    name: string;
    description: string;
    icon: string; // Lucide icon name or path
    color: string; // For UI accents
}

export type AnalysisStatus = 'pending' | 'analyzing' | 'complete' | 'error';
export type DocumentConfidence = 'high' | 'medium' | 'low';

export interface SmartAnalysisResult {
    fileId: string;
    fileName: string;
    fileSize: number;
    detectedTuneId?: string;
    confidence: DocumentConfidence;
    issues: string[]; // e.g., "Blurry", "Password Protected"
    isChild?: boolean; // If true, this is likely an attachment
    parentId?: string; // ID of the parent document
    previewUrl?: string; // Blob URL for preview
}

export interface DocumentGroup {
    id: string;
    mainDocument: SmartAnalysisResult;
    attachments: SmartAnalysisResult[];
}

export interface UploadState {
    step: 'tune-selection' | 'upload' | 'analysis' | 'review' | 'uploading' | 'complete';
    selectedTuneId: string | null;
    files: File[];
    analysisResults: SmartAnalysisResult[];
    groups: DocumentGroup[];
}
