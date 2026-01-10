// Ablage (Filing) System Types

export type CategoryType = 'entity' | 'folder' | 'custom';

export interface Category {
    id: string;
    name: string;
    type: CategoryType;
    parent_id?: string;
    document_count: number;
    icon?: string;
    color?: string;
    description?: string;
    created_at: string;
    updated_at: string;
}

export interface CategoryWithChildren extends Category {
    children?: CategoryWithChildren[];
}

export interface DocumentSummary {
    id: string;
    filename: string;
    document_type: string;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    confidence?: number;
    created_at: string;
    thumbnail_url?: string;
    preview_text?: string;
    tags?: string[];
    file_size?: number;
    page_count?: number;
}

// Upload Types
export type UploadStatus = 'pending' | 'uploading' | 'processing' | 'completed' | 'failed';

export interface UploadFile {
    id: string;
    file: File;
    status: UploadStatus;
    progress: number;
    error?: string;
    document_id?: string;
    preview?: string;
}

export interface UploadRequest {
    category_id?: string;
    ocr_backend: string;
    tags?: string[];
    auto_classify?: boolean;
    priority?: 'low' | 'normal' | 'high';
}

export interface UploadResponse {
    success: boolean;
    document_id: string;
    job_id: string;
    message: string;
}

export interface BatchUploadProgress {
    total: number;
    completed: number;
    failed: number;
    in_progress: number;
}

// OCR Backend Types
export interface OCRBackend {
    id: string;
    name: string;
    description: string;
    features: string[];
    accuracy: number;
    languages: number;
    recommended?: boolean;
    gpu_required: boolean;
    available: boolean;
}

// Category List Filter/Sort
export type DocumentSortField = 'name' | 'date' | 'type' | 'size' | 'confidence';
export type SortOrder = 'asc' | 'desc';

export interface CategoryDocumentFilter {
    search?: string;
    document_type?: string;
    status?: string;
    date_from?: string;
    date_to?: string;
    tags?: string[];
}

export interface CategoryDocumentListState {
    category: Category | null;
    documents: DocumentSummary[];
    loading: boolean;
    error?: string;
    sort_by: DocumentSortField;
    sort_order: SortOrder;
    filter: CategoryDocumentFilter;
    selected_ids: string[];
    view_mode: 'grid' | 'list';
}

// Available backends
export const OCR_BACKENDS: OCRBackend[] = [
    {
        id: 'got-ocr',
        name: 'GOT-OCR 2.0',
        description: 'State-of-the-art unified OCR mit Layout-Erkennung',
        features: ['LaTeX-Formeln', 'Tabellen', 'Bounding Boxes', 'Deutsche Texte'],
        accuracy: 98,
        languages: 25,
        recommended: true,
        gpu_required: true,
        available: true,
    },
    {
        id: 'surya-docling',
        name: 'Surya + Docling',
        description: 'Multilingual OCR mit Document Understanding',
        features: ['90+ Sprachen', 'Tabellen-Extraktion', 'Layout-Analyse'],
        accuracy: 96,
        languages: 90,
        gpu_required: true,
        available: true,
    },
    {
        id: 'deepseek-janus',
        name: 'DeepSeek Janus',
        description: 'Vision-Language Model für komplexe Dokumente',
        features: ['Kontextverständnis', 'Reasoning', 'Fraktur-Schrift'],
        accuracy: 94,
        languages: 15,
        gpu_required: true,
        available: true,
    },
    {
        id: 'cpu-fallback',
        name: 'CPU OCR (Tesseract)',
        description: 'Fallback ohne GPU-Anforderung',
        features: ['Keine GPU erforderlich', 'Langsamer'],
        accuracy: 85,
        languages: 100,
        gpu_required: false,
        available: true,
    },
];

// Helper Functions
export function getStatusColor(status: UploadStatus): string {
    switch (status) {
        case 'pending':
            return 'text-muted-foreground';
        case 'uploading':
            return 'text-blue-500';
        case 'processing':
            return 'text-yellow-500';
        case 'completed':
            return 'text-green-500';
        case 'failed':
            return 'text-red-500';
        default:
            return 'text-muted-foreground';
    }
}

export function getStatusLabel(status: UploadStatus): string {
    switch (status) {
        case 'pending':
            return 'Wartend';
        case 'uploading':
            return 'Wird hochgeladen...';
        case 'processing':
            return 'Wird verarbeitet...';
        case 'completed':
            return 'Abgeschlossen';
        case 'failed':
            return 'Fehlgeschlagen';
        default:
            return 'Unbekannt';
    }
}

export function formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}
