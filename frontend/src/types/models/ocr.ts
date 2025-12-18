/**
 * OCR Model Types
 *
 * Typen fuer OCR-Verarbeitung, Backends und Training.
 */

// ==================== OCR Backends ====================

/**
 * Available OCR backends
 */
export type OcrBackend = 'auto' | 'deepseek' | 'got_ocr' | 'surya' | 'surya_gpu';

/**
 * OCR backend information
 */
export interface OcrBackendInfo {
    id: OcrBackend;
    name: string;
    description: string;
    gpu_required: boolean;
    vram_gb: number;
    strengths: string[];
    recommended_for: string[];
}

/**
 * Available OCR backends with their capabilities
 */
export const OCR_BACKENDS: Record<OcrBackend, OcrBackendInfo> = {
    auto: {
        id: 'auto',
        name: 'Automatisch',
        description: 'Automatische Backend-Auswahl basierend auf Dokumenttyp',
        gpu_required: false,
        vram_gb: 0,
        strengths: ['Optimal fuer jeden Dokumenttyp'],
        recommended_for: ['Gemischte Dokumente', 'Unbekannte Layouts'],
    },
    deepseek: {
        id: 'deepseek',
        name: 'DeepSeek-Janus-Pro',
        description: 'Multimodales Vision-Language-Modell',
        gpu_required: true,
        vram_gb: 12,
        strengths: ['Beste Umlaut-Genauigkeit', 'Frakturschrift', 'Komplexe Layouts'],
        recommended_for: ['Deutsche Dokumente', 'Historische Texte', 'Formulare'],
    },
    got_ocr: {
        id: 'got_ocr',
        name: 'GOT-OCR 2.0',
        description: '600M Parameter Transformer-Modell',
        gpu_required: false,
        vram_gb: 10,
        strengths: ['Tabellen', 'Formeln', 'Schnell'],
        recommended_for: ['Rechnungen', 'Tabellarische Daten', 'Technische Dokumente'],
    },
    surya: {
        id: 'surya',
        name: 'Surya + Docling',
        description: 'Layout-aware OCR Pipeline (CPU)',
        gpu_required: false,
        vram_gb: 0,
        strengths: ['Layout-Analyse', 'CPU-basiert', 'Strukturerkennung'],
        recommended_for: ['CPU-only Umgebungen', 'Layout-kritische Dokumente'],
    },
    surya_gpu: {
        id: 'surya_gpu',
        name: 'Surya GPU',
        description: 'GPU-beschleunigte Variante von Surya',
        gpu_required: true,
        vram_gb: 4,
        strengths: ['Schnell', 'GPU-beschleunigt', 'Layout-Analyse'],
        recommended_for: ['Batch-Verarbeitung', 'Geschwindigkeit'],
    },
};

// ==================== OCR Processing ====================

/**
 * OCR processing options
 */
export interface OcrProcessingOptions {
    backend?: OcrBackend;
    language?: string;
    detect_tables?: boolean;
    detect_forms?: boolean;
    output_format?: 'text' | 'json' | 'hocr';
}

/**
 * OCR job status
 */
export type OcrJobStatus = 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';

/**
 * OCR job
 */
export interface OcrJob {
    id: string;
    document_id: string;
    status: OcrJobStatus;
    backend: OcrBackend;
    progress: number;
    started_at?: string;
    completed_at?: string;
    error?: string;
    processing_time_ms?: number;
}

/**
 * OCR result metadata
 */
export interface OcrResultMetadata {
    backend_used: OcrBackend;
    processing_time_ms: number;
    page_count: number;
    total_confidence: number;
    language_detected?: string;
    has_tables: boolean;
    has_forms: boolean;
}

// ==================== OCR Training ====================

/**
 * Training sample status
 */
export type TrainingSampleStatus = 'pending' | 'verified' | 'rejected';

/**
 * Training sample
 */
export interface TrainingSample {
    id: string;
    document_id: string;
    page_number: number;
    image_url: string;
    ground_truth_text: string;
    ocr_text?: string;
    status: TrainingSampleStatus;
    created_at: string;
    verified_at?: string;
    verified_by?: string;
}

/**
 * Training batch
 */
export interface TrainingBatch {
    id: string;
    name: string;
    sample_count: number;
    verified_count: number;
    created_at: string;
    status: 'active' | 'completed' | 'archived';
}

/**
 * Training statistics
 */
export interface TrainingStats {
    total_samples: number;
    verified_samples: number;
    pending_samples: number;
    rejected_samples: number;
    accuracy_improvement?: number;
}

// ==================== OCR Benchmark ====================

/**
 * Benchmark result for single backend
 */
export interface BackendBenchmarkResult {
    backend: OcrBackend;
    cer: number; // Character Error Rate
    wer: number; // Word Error Rate
    umlaut_accuracy: number;
    processing_time_ms: number;
    samples_processed: number;
}

/**
 * Benchmark comparison
 */
export interface BenchmarkComparison {
    run_id: string;
    run_date: string;
    sample_count: number;
    results: BackendBenchmarkResult[];
    winner: OcrBackend;
    winner_reason: string;
}

// ==================== OCR Metrics ====================

/**
 * OCR quality metrics
 */
export interface OcrQualityMetrics {
    average_confidence: number;
    character_error_rate: number;
    word_error_rate: number;
    umlaut_accuracy: number;
    processing_time_avg_ms: number;
    documents_processed: number;
    period: string;
}

/**
 * Backend usage statistics
 */
export interface BackendUsageStats {
    backend: OcrBackend;
    usage_count: number;
    usage_percentage: number;
    avg_confidence: number;
    avg_processing_time_ms: number;
}

// ==================== ML Router ====================

/**
 * ML Router decision
 */
export interface MlRouterDecision {
    selected_backend: OcrBackend;
    confidence: number;
    reason: string;
    alternatives: Array<{
        backend: OcrBackend;
        score: number;
    }>;
}

/**
 * ML Router weights
 */
export interface MlRouterWeights {
    backend: OcrBackend;
    weight: number;
    last_updated: string;
}
