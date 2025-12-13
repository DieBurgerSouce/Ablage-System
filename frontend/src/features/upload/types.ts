/**
 * Upload-Status für einzelne Dateien
 */
export type UploadFileStatus =
    | 'pending'
    | 'uploading'
    | 'processing'
    | 'awaiting_confirmation'  // Nach OCR, Klassifizierung anzeigen
    | 'completed'
    | 'failed';

/**
 * Invoice Direction (Rechnungsrichtung)
 */
export type InvoiceDirection = 'incoming' | 'outgoing' | 'unknown';

/**
 * Klassifizierung nach OCR-Verarbeitung
 */
export interface DocumentClassification {
    /** Erkannte Rechnungsrichtung */
    invoiceDirection: InvoiceDirection;
    /** Konfidenz der Erkennung (0-1) */
    confidence: number;
    /** Begründung für die Erkennung */
    reason?: string;
}

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
    /** Klassifizierung nach OCR (Eingangs-/Ausgangsrechnung) */
    classification?: DocumentClassification;
    /** Vom Benutzer bestätigte/korrigierte Richtung */
    confirmedDirection?: 'incoming' | 'outgoing';
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
 * Tag Interface.
 * Wird für Dokumenten-Kategorisierung und optionale Tune-Verknüpfung verwendet.
 */
export interface Tag {
    id: string;
    name: string;
    description: string | null;
    icon: string;
    color: string | null;
    tune_id: string | null;
    is_system: boolean;
    is_active: boolean;
    created_at?: string;
    updated_at?: string | null;
}

/**
 * Tag Create/Update Schemas
 */
export interface TagCreate {
    name: string;
    description?: string;
    icon?: string;
    color?: string;
    tune_id?: string;
    is_active?: boolean;
}

export interface TagUpdate {
    name?: string;
    description?: string;
    icon?: string;
    color?: string;
    tune_id?: string | null;
    is_active?: boolean;
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
