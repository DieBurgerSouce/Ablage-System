/**
 * Zentrale Backend-Konfiguration für OCR-Training
 * Diese Datei eliminiert die 6-fache Duplikation der Backend-Definitionen
 */

export const BACKEND_CONFIG = {
    'deepseek-janus-pro': {
        displayName: 'DeepSeek-Janus-Pro',
        vramGB: 12,
        requiresGPU: true,
        color: '#8884d8',
        description: 'Multimodales Vision-Language-Modell mit bester Umlaut-Genauigkeit',
        strengths: [
            'Umlaute (ä, ö, ü, ß)',
            'Frakturschrift',
            'Komplexe Layouts',
            'Deutsche Texte',
        ],
        weaknesses: [
            'Hoher VRAM-Bedarf (12GB)',
            'Langsamer als GOT-OCR',
        ],
    },
    'got-ocr-2.0': {
        displayName: 'GOT-OCR 2.0',
        vramGB: 10,
        requiresGPU: true,
        color: '#82ca9d',
        description: '600M Parameter Transformer-Modell für schnelle Verarbeitung',
        strengths: [
            'Tabellen-Erkennung',
            'Mathematische Formeln',
            'Schnelle Verarbeitung',
            'Strukturierte Dokumente',
        ],
        weaknesses: [
            'Umlaut-Probleme bei Fraktur',
            'Benötigt GPU',
        ],
    },
    'surya-gpu': {
        displayName: 'Surya GPU',
        vramGB: 4,
        requiresGPU: true,
        color: '#ffc658',
        description: 'Schnelle GPU-Variante mit Layout-Analyse',
        strengths: [
            'Niedriger VRAM-Bedarf',
            'Layout-Analyse',
            'Schnelle Batch-Verarbeitung',
        ],
        weaknesses: [
            'Geringere Genauigkeit',
            'Umlaute weniger zuverlässig',
        ],
    },
    'surya': {
        displayName: 'Surya (CPU)',
        vramGB: 0,
        requiresGPU: false,
        color: '#ff8042',
        description: 'CPU-Fallback mit Docling-Integration für Layout-Analyse',
        strengths: [
            'Keine GPU erforderlich',
            'Stabil und zuverlässig',
            'Layout-Analyse mit Docling',
        ],
        weaknesses: [
            'Langsamer als GPU-Varianten',
            'Eingeschränkte Genauigkeit',
        ],
    },
} as const;

export type BackendId = keyof typeof BACKEND_CONFIG;
export type BackendConfig = typeof BACKEND_CONFIG[BackendId];

export const BACKEND_IDS = Object.keys(BACKEND_CONFIG) as BackendId[];

export const BACKEND_COLORS: Record<BackendId, string> = Object.fromEntries(
    Object.entries(BACKEND_CONFIG).map(([id, cfg]) => [id, cfg.color])
) as Record<BackendId, string>;

/**
 * Holt die Konfiguration für ein Backend mit Fallback
 */
export function getBackendConfig(backendId: string): BackendConfig | undefined {
    return BACKEND_CONFIG[backendId as BackendId];
}

/**
 * Holt den Display-Namen für ein Backend
 */
export function getBackendDisplayName(backendId: string): string {
    return BACKEND_CONFIG[backendId as BackendId]?.displayName ?? backendId;
}

/**
 * Holt die Farbe für ein Backend
 */
export function getBackendColor(backendId: string): string {
    return BACKEND_CONFIG[backendId as BackendId]?.color ?? '#888888';
}

/**
 * Maximaler VRAM der RTX 4080
 */
export const MAX_VRAM_GB = 16;

/**
 * VRAM-Warnschwelle (85%)
 */
export const VRAM_WARNING_THRESHOLD = 0.85;
