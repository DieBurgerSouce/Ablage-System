/**
 * Hook für Feld-Korrekturen im Review-Workflow.
 *
 * Verwaltet:
 * - Lokalen State für Korrekturen
 * - Auto-Detection des CorrectionType
 * - Bestätigung von Feldern
 * - Batch-Submit an API
 */

import { useState, useCallback, useMemo } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'
import type { FieldCorrection, CorrectionType, CorrectionCreate } from '../types'

// Patterns für CorrectionType-Erkennung
const UMLAUT_PATTERN = /[äöüÄÖÜß]/
const DATE_PATTERN = /^\d{1,2}[./]\d{1,2}[./]\d{2,4}$|^\d{4}-\d{2}-\d{2}$/
const AMOUNT_PATTERN = /^\d+[.,]?\d*\s*€?$|^\d{1,3}(\.\d{3})*(,\d{2})?$/
const IBAN_PATTERN = /^[A-Z]{2}\d{2}[A-Z0-9]{4,}/i

// Felder die typischerweise bestimmte CorrectionTypes haben
const FIELD_TYPE_MAP: Record<string, CorrectionType> = {
    invoice_date: 'DATE',
    due_date: 'DATE',
    service_period_start: 'DATE',
    service_period_end: 'DATE',
    discount_due_date: 'DATE',
    net_amount: 'AMOUNT',
    vat_amount: 'AMOUNT',
    gross_amount: 'AMOUNT',
    discount_amount: 'AMOUNT',
    invoice_number: 'NUMBER',
    order_number: 'NUMBER',
    customer_number: 'NUMBER',
    supplier_number: 'NUMBER',
    sender_iban: 'IBAN',
    sender_vat_id: 'VAT_ID',
    recipient_vat_id: 'VAT_ID',
    sender_company: 'NAME',
    recipient_company: 'NAME',
    sender_person: 'NAME',
    recipient_person: 'NAME',
}

/**
 * Erkennt automatisch den CorrectionType basierend auf Feldname und Wert.
 */
function detectCorrectionType(
    field: string,
    originalValue: string | number | null,
    correctedValue: string | number | null
): CorrectionType {
    // 1. Prüfe Feld-basierte Zuordnung
    if (field in FIELD_TYPE_MAP) {
        return FIELD_TYPE_MAP[field]
    }

    // 2. Prüfe Wert-basierte Erkennung
    const original = String(originalValue || '')
    const corrected = String(correctedValue || '')

    // Umlaut-Korrektur
    if (!UMLAUT_PATTERN.test(original) && UMLAUT_PATTERN.test(corrected)) {
        return 'UMLAUT'
    }

    // Datum-Korrektur
    if (DATE_PATTERN.test(corrected)) {
        return 'DATE'
    }

    // Betrags-Korrektur
    if (AMOUNT_PATTERN.test(corrected)) {
        return 'AMOUNT'
    }

    // IBAN-Korrektur
    if (IBAN_PATTERN.test(corrected)) {
        return 'IBAN'
    }

    // Fallback
    return 'GENERAL'
}

/**
 * Feld-Labels für deutsche UI
 */
const FIELD_LABELS: Record<string, string> = {
    invoice_number: 'Rechnungsnummer',
    invoice_date: 'Rechnungsdatum',
    due_date: 'Fälligkeitsdatum',
    net_amount: 'Nettobetrag',
    vat_amount: 'MwSt-Betrag',
    gross_amount: 'Bruttobetrag',
    vat_rate: 'MwSt-Satz',
    sender_company: 'Absender Firma',
    sender_street: 'Absender Straße',
    sender_zip_code: 'Absender PLZ',
    sender_city: 'Absender Stadt',
    recipient_company: 'Empfänger Firma',
    recipient_street: 'Empfänger Straße',
    recipient_zip_code: 'Empfänger PLZ',
    recipient_city: 'Empfänger Stadt',
    sender_vat_id: 'USt-IdNr Absender',
    recipient_vat_id: 'USt-IdNr Empfänger',
    sender_iban: 'IBAN',
    sender_bic: 'BIC',
    payment_terms: 'Zahlungsbedingungen',
    payment_terms_days: 'Zahlungsfrist (Tage)',
    discount_percent: 'Skonto (%)',
    discount_days: 'Skontofrist (Tage)',
    order_number: 'Bestellnummer',
    customer_number: 'Kundennummer',
}

interface UseFieldCorrectionsOptions {
    sampleId?: string
    documentId?: string | null
    backendUsed?: string
}

/**
 * Hook zum Verwalten von Feld-Korrekturen.
 */
export function useFieldCorrections(options: UseFieldCorrectionsOptions = {}) {
    const { sampleId, documentId, backendUsed = 'unknown' } = options

    // State: Map von field -> FieldCorrection
    const [corrections, setCorrections] = useState<Map<string, FieldCorrection>>(new Map())

    // State: Set von bestätigten Feldern
    const [confirmedFields, setConfirmedFields] = useState<Set<string>>(new Set())

    // Mutation für Batch-Submit
    const submitMutation = useMutation({
        mutationFn: async (correctionData: CorrectionCreate[]) => {
            // Submit jede Korrektur einzeln
            const results = await Promise.all(
                correctionData.map(correction =>
                    apiClient.post('/training/corrections', correction)
                )
            )
            return results
        },
    })

    /**
     * Setzt eine Korrektur für ein Feld.
     */
    const setCorrection = useCallback((
        field: string,
        originalValue: string | number | null,
        correctedValue: string | number | null
    ) => {
        const correctionType = detectCorrectionType(field, originalValue, correctedValue)

        setCorrections(prev => {
            const next = new Map(prev)
            next.set(field, {
                field,
                fieldLabel: FIELD_LABELS[field] || field,
                originalValue,
                correctedValue,
                correctionType,
                timestamp: new Date().toISOString(),
            })
            return next
        })

        // Entferne aus bestätigt wenn korrigiert
        setConfirmedFields(prev => {
            const next = new Set(prev)
            next.delete(field)
            return next
        })
    }, [])

    /**
     * Entfernt eine Korrektur (Rückgängig).
     */
    const removeCorrection = useCallback((field: string) => {
        setCorrections(prev => {
            const next = new Map(prev)
            next.delete(field)
            return next
        })
    }, [])

    /**
     * Bestätigt ein Feld ohne Korrektur.
     */
    const confirmField = useCallback((field: string) => {
        setConfirmedFields(prev => {
            const next = new Set(prev)
            next.add(field)
            return next
        })

        // Entferne aus Korrekturen wenn bestätigt
        setCorrections(prev => {
            const next = new Map(prev)
            next.delete(field)
            return next
        })
    }, [])

    /**
     * Bestätigt alle Felder ohne Korrektur.
     */
    const confirmAllFields = useCallback((fields: string[]) => {
        setConfirmedFields(prev => {
            const next = new Set(prev)
            fields.forEach(f => next.add(f))
            return next
        })
    }, [])

    /**
     * Entfernt Bestätigung eines Feldes.
     */
    const unconfirmField = useCallback((field: string) => {
        setConfirmedFields(prev => {
            const next = new Set(prev)
            next.delete(field)
            return next
        })
    }, [])

    /**
     * Setzt alle Korrekturen und Bestätigungen zurück.
     */
    const reset = useCallback(() => {
        setCorrections(new Map())
        setConfirmedFields(new Set())
    }, [])

    /**
     * Submitted alle Korrekturen an die API.
     */
    const submitCorrections = useCallback(async () => {
        if (corrections.size === 0) {
            return { success: true, submitted: 0 }
        }

        const correctionData: CorrectionCreate[] = Array.from(corrections.values()).map(c => ({
            document_id: documentId || undefined,
            training_sample_id: sampleId,
            original_text: String(c.originalValue || ''),
            corrected_text: String(c.correctedValue || ''),
            correction_type: c.correctionType,
            field_corrected: c.field,
            backend_used: backendUsed,
            applies_to_training: true,
        }))

        await submitMutation.mutateAsync(correctionData)

        return {
            success: true,
            submitted: correctionData.length,
        }
    }, [corrections, documentId, sampleId, backendUsed, submitMutation])

    // Computed Values
    const hasCorrections = corrections.size > 0
    const correctionCount = corrections.size
    const confirmedCount = confirmedFields.size
    const correctionsList = useMemo(() => Array.from(corrections.values()), [corrections])

    // Hilfsfunktionen
    const isFieldCorrected = useCallback((field: string) => corrections.has(field), [corrections])
    const isFieldConfirmed = useCallback((field: string) => confirmedFields.has(field), [confirmedFields])
    const getCorrection = useCallback((field: string) => corrections.get(field), [corrections])

    return {
        // State
        corrections,
        confirmedFields,
        correctionsList,

        // Actions
        setCorrection,
        removeCorrection,
        confirmField,
        confirmAllFields,
        unconfirmField,
        reset,
        submitCorrections,

        // Helpers
        isFieldCorrected,
        isFieldConfirmed,
        getCorrection,
        hasCorrections,
        correctionCount,
        confirmedCount,

        // Submit State
        isSubmitting: submitMutation.isPending,
        submitError: submitMutation.error,
    }
}

export type UseFieldCorrectionsReturn = ReturnType<typeof useFieldCorrections>
