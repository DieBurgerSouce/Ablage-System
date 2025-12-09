/**
 * Tune (Dokument-Kontext) Interface.
 * Tunes definieren kontextspezifische Verarbeitungsregeln für Dokumente.
 */
export interface Tune {
    id: string;
    name: string;
    description: string | null;
    icon: string; // Lucide icon name (e.g., "FileText", "Receipt")
    color: string; // Tailwind color class (e.g., "bg-slate-500")
    prompt_template?: string | null; // Custom system prompt for this tune
    default_backend?: string | null; // Preferred OCR backend
    is_system: boolean; // System tunes cannot be deleted
    is_active: boolean; // Inactive tunes are hidden from selection
    created_at?: string; // ISO timestamp
    updated_at?: string | null; // ISO timestamp
}

export type AnalysisStatus = 'pending' | 'analyzing' | 'complete' | 'error';
export type DocumentConfidence = 'high' | 'medium' | 'low';

export interface SmartAnalysisResult {
    fileId: string;
    fileName: string;
    fileSize: number;
    detectedTuneId?: string;
    selectedBackendId?: string; // The backend chosen for this specific document
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
    step: 'upload' | 'analysis' | 'review' | 'uploading' | 'complete';
    selectedBackendId: string | null;
    selectedTuneId: string | null;
    files: File[];
    analysisResults: SmartAnalysisResult[];
    groups: DocumentGroup[];
}
