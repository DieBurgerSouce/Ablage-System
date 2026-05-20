/**
 * Company-Setup-Wizard Utilities
 *
 * Hilfsfunktionen für den Company-Setup-Wizard.
 * Enterprise-Grade: Mit localStorage/sessionStorage Fallback für Privacy Mode.
 */

import { logger } from '@/lib/logger'

export const STORAGE_KEY = 'ablage_company_setup_complete'
export const STORAGE_KEY_SKIPPED = 'ablage_company_setup_skipped'

// ==================== Storage Helpers ====================

/**
 * Sicherer Storage-Zugriff mit Fallback
 * Unterstützt localStorage → sessionStorage → Memory Fallback
 */
const memoryStorage: Record<string, string> = {}

function safeGetItem(key: string): string | null {
    try {
        return localStorage.getItem(key)
    } catch {
        // localStorage nicht verfügbar (Privacy Mode)
        try {
            return sessionStorage.getItem(key)
        } catch {
            // Auch sessionStorage nicht verfügbar
            return memoryStorage[key] || null
        }
    }
}

function safeSetItem(key: string, value: string): void {
    try {
        localStorage.setItem(key, value)
    } catch {
        // localStorage nicht verfügbar (Privacy Mode)
        try {
            sessionStorage.setItem(key, value)
        } catch {
            // Auch sessionStorage nicht verfügbar - Memory Fallback
            memoryStorage[key] = value
            logger.warn('Speicher nicht verfügbar, nutze Memory Fallback')
        }
    }
}

function safeRemoveItem(key: string): void {
    try {
        localStorage.removeItem(key)
    } catch {
        // Ignore
    }
    try {
        sessionStorage.removeItem(key)
    } catch {
        // Ignore
    }
    delete memoryStorage[key]
}

// ==================== Public API ====================

/**
 * Setzt den Company-Setup-Status zurück
 */
export function resetCompanySetup(): void {
    safeRemoveItem(STORAGE_KEY)
    safeRemoveItem(STORAGE_KEY_SKIPPED)
}

/**
 * Prüft ob das Company-Setup abgeschlossen ist
 */
export function isCompanySetupComplete(): boolean {
    return safeGetItem(STORAGE_KEY) === 'true'
}

/**
 * Prüft ob das Company-Setup übersprungen wurde
 */
export function isCompanySetupSkipped(): boolean {
    return safeGetItem(STORAGE_KEY_SKIPPED) === 'true'
}

/**
 * Markiert das Company-Setup als abgeschlossen
 */
export function markCompanySetupComplete(): void {
    safeSetItem(STORAGE_KEY, 'true')
    safeRemoveItem(STORAGE_KEY_SKIPPED)
}

/**
 * Markiert das Company-Setup als übersprungen
 */
export function markCompanySetupSkipped(): void {
    safeSetItem(STORAGE_KEY_SKIPPED, 'true')
}
