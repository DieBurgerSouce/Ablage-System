/**
 * Upload-Status für einzelne Dateien
 */
export type UploadFileStatus = 'pending' | 'uploading' | 'processing' | 'completed' | 'failed';

/**
 * Repräsentiert eine Datei im Upload-Prozess
 */
export interface UploadingFile {
    /** Eindeutige ID für React key */
    id: string;
    /** Original File-Objekt */
    file: File;
    /** Aktueller Status */
    status: UploadFileStatus;
    /** Upload-Fortschritt (0-100) */
    progress: number;
    /** Fehlermeldung bei 'failed' */
    error?: string;
    /** Backend-Dokument-ID nach erfolgreichem Upload */
    documentId?: string;
    /** Celery Task ID für OCR Progress Tracking */
    taskId?: string;
    /** OCR-Fortschritt (0-100) während 'processing' */
    ocrProgress?: number;
    /** OCR Status-Nachricht vom Backend */
    ocrMessage?: string;
}

/**
 * Tune (Dokument-Kontext) Interface.
 * Wird vom Admin-Bereich für Tune-Management verwendet.
 */
export interface Tune {
    id: string;
    name: string;
    description: string | null;
    icon: string;
    color: string;
    prompt_template?: string | null;
    default_backend?: string | null;
    is_system: boolean;
    is_active: boolean;
    created_at?: string;
    updated_at?: string | null;
}

/**
 * @deprecated Nicht mehr verwendet - nur für Rückwärtskompatibilität
 */
export type SmartAnalysisResult = {
    fileId: string;
    fileName: string;
    fileSize: number;
    detectedTuneId?: string;
    selectedBackendId?: string;
    confidence: 'high' | 'medium' | 'low';
    issues: string[];
    isChild?: boolean;
    parentId?: string;
    previewUrl?: string;
}
