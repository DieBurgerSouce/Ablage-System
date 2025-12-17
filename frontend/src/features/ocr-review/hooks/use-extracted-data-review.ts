/**
 * Hook fuer ExtractedData im Review-Kontext.
 *
 * Laedt ExtractedDocumentData fuer ein Sample und extrahiert:
 * - Low-Confidence Felder (< 70%)
 * - Validierungsfehler (IBAN, Summen, etc.)
 * - Flag-Gruende aus dem Queue-Item
 */

import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { extractedDataApi } from '@/features/extracted-data/api/extracted-data-api'
import type { ExtractedDocumentData, ExtractedInvoiceData } from '@/features/extracted-data/types/extracted-data.types'
import type { QueueItem, FlagReason, ValidationError } from '../types'

// Konfidenz-Schwellwert fuer "low confidence"
const CONFIDENCE_THRESHOLD = 0.70

// Feld-Labels fuer deutsche UI
const FIELD_LABELS: Record<string, string> = {
    invoice_number: 'Rechnungsnummer',
    invoice_date: 'Rechnungsdatum',
    due_date: 'Faelligkeitsdatum',
    net_amount: 'Nettobetrag',
    vat_amount: 'MwSt-Betrag',
    gross_amount: 'Bruttobetrag',
    vat_rate: 'MwSt-Satz',
    sender_company: 'Absender Firma',
    sender_street: 'Absender Strasse',
    sender_zip: 'Absender PLZ',
    sender_city: 'Absender Stadt',
    recipient_company: 'Empfaenger Firma',
    recipient_street: 'Empfaenger Strasse',
    recipient_zip: 'Empfaenger PLZ',
    recipient_city: 'Empfaenger Stadt',
    sender_vat_id: 'USt-IdNr Absender',
    recipient_vat_id: 'USt-IdNr Empfaenger',
    sender_iban: 'IBAN',
    sender_bic: 'BIC',
    payment_terms: 'Zahlungsbedingungen',
    payment_terms_days: 'Zahlungsfrist (Tage)',
    discount_percent: 'Skonto (%)',
    discount_days: 'Skontofrist (Tage)',
    order_number: 'Bestellnummer',
    customer_number: 'Kundennummer',
}

/**
 * Extrahiert Low-Confidence Felder aus den Validierungen.
 */
function extractLowConfidenceFields(
    invoice: ExtractedInvoiceData | null | undefined,
    threshold: number = CONFIDENCE_THRESHOLD
): string[] {
    if (!invoice?.validations?.field_confidence) {
        return []
    }

    const lowConfidence: string[] = []
    for (const [field, confidence] of Object.entries(invoice.validations.field_confidence)) {
        if (typeof confidence === 'number' && confidence < threshold) {
            lowConfidence.push(field)
        }
    }
    return lowConfidence
}

/**
 * Extrahiert Validierungsfehler aus ExtractedInvoiceData.
 */
function extractValidationErrors(
    invoice: ExtractedInvoiceData | null | undefined
): ValidationError[] {
    const errors: ValidationError[] = []

    if (!invoice?.validations) {
        return errors
    }

    const v = invoice.validations

    // IBAN-Checksum
    if (v.iban_checksum_valid === false) {
        errors.push({
            field: 'sender_iban',
            fieldLabel: FIELD_LABELS.sender_iban || 'IBAN',
            error: 'IBAN-Pruefziffer ungueltig',
            severity: 'error',
        })
    }

    // IBAN-Land stimmt nicht mit Absender-Land ueberein
    if (v.iban_country_match === false) {
        errors.push({
            field: 'sender_iban',
            fieldLabel: FIELD_LABELS.sender_iban || 'IBAN',
            error: 'IBAN-Land stimmt nicht mit Absender-Land ueberein',
            severity: 'warning',
        })
    }

    // Summen stimmen nicht
    if (v.sums_match === false) {
        const diff = v.sums_difference
        const diffText = diff !== undefined && diff !== null
            ? ` (Differenz: ${Number(diff).toFixed(2)} EUR)`
            : ''
        errors.push({
            field: 'gross_amount',
            fieldLabel: FIELD_LABELS.gross_amount || 'Bruttobetrag',
            error: `Summen stimmen nicht ueberein${diffText}`,
            severity: 'error',
        })
    }

    // USt-ID ungueltig (VIES)
    if (v.vies_vat_valid === false) {
        errors.push({
            field: 'sender_vat_id',
            fieldLabel: FIELD_LABELS.sender_vat_id || 'USt-IdNr',
            error: 'USt-IdNr konnte nicht validiert werden (VIES)',
            severity: 'warning',
        })
    }

    // USt-ID-Land stimmt nicht mit Absender-Land ueberein
    if (v.vat_country_match === false) {
        errors.push({
            field: 'sender_vat_id',
            fieldLabel: FIELD_LABELS.sender_vat_id || 'USt-IdNr',
            error: 'USt-IdNr-Land stimmt nicht mit Absender-Land ueberein',
            severity: 'warning',
        })
    }

    return errors
}

/**
 * Berechnet Flag-Gruende aus QueueItem und ExtractedData.
 */
function computeFlagReasons(
    queueItem: QueueItem | null | undefined,
    _extractedData: ExtractedDocumentData | null,
    lowConfidenceFields: string[],
    validationErrors: ValidationError[]
): FlagReason[] {
    const reasons: FlagReason[] = []

    if (!queueItem) return reasons

    // Parse reason string vom Backend
    const reasonParts = queueItem.reason.split(', ')

    // Coverage-Luecke
    if (reasonParts.some(r => r.includes('Coverage-Luecke'))) {
        const match = queueItem.reason.match(/Coverage-Luecke \((\d+)%\)/)
        const coverage = match ? match[1] : '?'
        reasons.push({
            type: 'coverage_gap',
            label: 'Coverage-Luecke',
            details: `Coverage fuer "${queueItem.document_type}" bei ${coverage}% (Ziel: 90%)`,
            severity: 'critical',
        })
    }

    // Stichproben-Review
    if (queueItem.is_spot_check) {
        reasons.push({
            type: 'spot_check',
            label: 'Stichprobe',
            details: 'Zufaellig ausgewaehlte Stichprobe aus Auto-Accepted Samples',
            severity: 'medium',
        })
    }

    // Niedrige Confidence
    if (reasonParts.some(r => r.includes('Niedrige Confidence'))) {
        const match = queueItem.reason.match(/Niedrige Confidence \((\d+)%\)/)
        const conf = match ? match[1] : String(Math.round(queueItem.confidence * 100))
        reasons.push({
            type: 'low_confidence',
            label: 'Niedrige Konfidenz',
            details: `OCR-Konfidenz bei ${conf}%`,
            severity: 'high',
            affectedFields: lowConfidenceFields,
        })
    }

    // Geschaeftskritisch (Rechnung)
    if (reasonParts.some(r => r.includes('Geschaeftskritisch'))) {
        reasons.push({
            type: 'business_critical',
            label: 'Geschaeftskritisch',
            details: 'Rechnung - erhoehte Prioritaet fuer Buchhaltung',
            severity: 'high',
        })
    }

    // Validierungsfehler
    if (validationErrors.length > 0) {
        const errorFields = validationErrors.map(e => e.fieldLabel).join(', ')
        reasons.push({
            type: 'validation_error',
            label: 'Validierungsfehler',
            details: `${validationErrors.length} Fehler gefunden: ${errorFields}`,
            severity: validationErrors.some(e => e.severity === 'error') ? 'critical' : 'high',
            affectedFields: validationErrors.map(e => e.field),
        })
    }

    // Low-Confidence Felder hinzufuegen wenn nicht schon erfasst
    if (lowConfidenceFields.length > 0 && !reasons.some(r => r.type === 'low_confidence')) {
        const fieldLabels = lowConfidenceFields.map(f => FIELD_LABELS[f] || f).join(', ')
        reasons.push({
            type: 'low_confidence',
            label: 'Unsichere Felder',
            details: `${lowConfidenceFields.length} Felder mit niedriger Konfidenz: ${fieldLabels}`,
            severity: 'medium',
            affectedFields: lowConfidenceFields,
        })
    }

    return reasons
}

/**
 * Hook um ExtractedDocumentData fuer Review zu laden.
 *
 * NEU: Nutzt extracted_data direkt aus QueueItem wenn vorhanden,
 * faellt zurueck auf API-Call wenn document_id existiert.
 */
export function useExtractedDataForReview(
    documentId: string | null | undefined,
    queueItem: QueueItem | null | undefined
) {
    // Pruefe ob extracted_data direkt im QueueItem vorhanden ist
    const hasInlineData = !!queueItem?.extracted_data

    // Query fuer ExtractedData - nur wenn keine Inline-Daten UND document_id existiert
    const {
        data: fetchedData,
        isLoading: isFetching,
        error,
        refetch,
    } = useQuery({
        queryKey: ['extracted-data-review', documentId],
        queryFn: () => extractedDataApi.getByDocumentId(documentId!),
        enabled: !hasInlineData && !!documentId,  // Nur laden wenn keine Inline-Daten
        staleTime: 5 * 60 * 1000, // 5 Minuten Cache
        retry: 1,
    })

    // Nutze Inline-Daten (aus QueueItem) oder gefetchte Daten
    const extractedData = useMemo(() => {
        if (hasInlineData) {
            // Daten direkt aus QueueItem (vom Backend mitgeliefert)
            return queueItem?.extracted_data as ExtractedDocumentData | null
        }
        return fetchedData || null
    }, [hasInlineData, queueItem?.extracted_data, fetchedData])

    // Loading-Status: nur wenn wir wirklich fetchen
    const isLoading = !hasInlineData && isFetching

    // Extrahiere Invoice-Daten (wenn vorhanden)
    const invoiceData = extractedData?.invoice || null

    // Berechne abgeleitete Daten
    const lowConfidenceFields = useMemo(
        () => extractLowConfidenceFields(invoiceData),
        [invoiceData]
    )

    const validationErrors = useMemo(
        () => extractValidationErrors(invoiceData),
        [invoiceData]
    )

    const flagReasons = useMemo(
        () => computeFlagReasons(queueItem, extractedData || null, lowConfidenceFields, validationErrors),
        [queueItem, extractedData, lowConfidenceFields, validationErrors]
    )

    // Confidence-Map fuer schnellen Zugriff
    const fieldConfidenceMap = useMemo(() => {
        const map = new Map<string, number>()
        if (invoiceData?.validations?.field_confidence) {
            for (const [field, conf] of Object.entries(invoiceData.validations.field_confidence)) {
                if (typeof conf === 'number') {
                    map.set(field, conf)
                }
            }
        }
        return map
    }, [invoiceData])

    return {
        // Data
        extractedData: extractedData || null,
        invoiceData,
        orderData: extractedData?.order || null,
        contractData: extractedData?.contract || null,

        // Derived
        lowConfidenceFields,
        validationErrors,
        flagReasons,
        fieldConfidenceMap,

        // Helpers
        hasExtractedData: !!extractedData,
        documentType: extractedData?.classification?.document_type || queueItem?.document_type,
        overallConfidence: extractedData?.overall_confidence,

        // Query State
        isLoading,
        error,
        refetch,

        // Field Label Helper
        getFieldLabel: (field: string) => FIELD_LABELS[field] || field,
        isLowConfidence: (field: string) => lowConfidenceFields.includes(field),
        getFieldConfidence: (field: string) => fieldConfidenceMap.get(field),
        hasValidationError: (field: string) => validationErrors.some(e => e.field === field),
        getValidationError: (field: string) => validationErrors.find(e => e.field === field),
    }
}

export type UseExtractedDataForReviewReturn = ReturnType<typeof useExtractedDataForReview>
