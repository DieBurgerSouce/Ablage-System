/**
 * Hook für ExtractedData im Review-Kontext.
 *
 * Lädt ExtractedDocumentData für ein Sample und extrahiert:
 * - Low-Confidence Felder (< 70%)
 * - Validierungsfehler (IBAN, Summen, etc.)
 * - Flag-Gründe aus dem Queue-Item
 */

import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { extractedDataApi } from '@/features/extracted-data/api/extracted-data-api'
import type { ExtractedDocumentData, ExtractedInvoiceData } from '@/features/extracted-data/types/extracted-data.types'
import type { QueueItem, FlagReason, ValidationError } from '../types'

// Konfidenz-Schwellwert für "low confidence"
const CONFIDENCE_THRESHOLD = 0.70

// Feld-Labels für deutsche UI
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
    sender_zip: 'Absender PLZ',
    sender_city: 'Absender Stadt',
    recipient_company: 'Empfänger Firma',
    recipient_street: 'Empfänger Straße',
    recipient_zip: 'Empfänger PLZ',
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
 * Prüft ob ein Wert als "leer" gilt.
 * Erkennt: null, undefined, "", "-", "n/a", "none", etc.
 */
function isEmptyValue(value: unknown): boolean {
    if (value === null || value === undefined) return true
    if (typeof value === 'string') {
        const trimmed = value.trim().toLowerCase()
        return trimmed === '' || trimmed === '-' || trimmed === 'n/a' || trimmed === 'none' || trimmed === 'k.a.'
    }
    if (typeof value === 'number') {
        return false // Zahlen sind nie "leer" (auch 0 ist ein gültiger Wert)
    }
    return false
}

/**
 * Extrahiert ALLE Validierungsfehler aus ExtractedInvoiceData.
 * Professionelles System mit drei Severity-Levels:
 * - error: Kritisch, muss korrigiert werden
 * - warning: Wichtig, sollte geprüft werden
 * - info: Hinweis, optional
 */
function extractValidationErrors(
    invoice: ExtractedInvoiceData | null | undefined
): ValidationError[] {
    const errors: ValidationError[] = []

    if (!invoice) {
        return errors
    }

    // Helper: Feld prüfen und bei leerem Wert Fehler hinzufügen
    const checkField = (
        field: string,
        value: unknown,
        _severity: 'error',  // Immer 'error' - Parameter für Kompatibilität behalten
        customError?: string
    ) => {
        if (isEmptyValue(value) && !errors.some(e => e.field === field)) {
            errors.push({
                field,
                fieldLabel: FIELD_LABELS[field] || field,
                error: customError || 'Nicht erkannt',
                severity: 'error',
            })
        }
    }

    const v = invoice.validations

    // ═══════════════════════════════════════════════════════════════
    // 1. BACKEND-VALIDIERUNGEN (höchste Priorität)
    // ═══════════════════════════════════════════════════════════════

    if (v) {
        // IBAN-Checksum ungültig
        if (v.iban_checksum_valid === false) {
            errors.push({
                field: 'sender_iban',
                fieldLabel: FIELD_LABELS.sender_iban || 'IBAN',
                error: 'IBAN-Prüfziffer ungültig',
                severity: 'error',
            })
        }

        // Positionssumme vs Nettobetrag stimmen nicht
        if (v.sums_match === false) {
            const diff = v.sums_difference
            const diffText = diff !== undefined && diff !== null
                ? ` (Diff: ${Number(diff).toFixed(2)} EUR)`
                : ''
            errors.push({
                field: 'net_amount',
                fieldLabel: 'Positionssumme',
                error: `Weicht vom Nettobetrag ab${diffText}`,
                severity: 'error',
            })
        }

        // IBAN-Land stimmt nicht
        if (v.iban_country_match === false) {
            errors.push({
                field: 'sender_iban',
                fieldLabel: FIELD_LABELS.sender_iban || 'IBAN',
                error: 'IBAN-Land stimmt nicht überein',
                severity: 'error',
            })
        }

        // USt-ID ungültig (VIES)
        if (v.vies_vat_valid === false) {
            errors.push({
                field: 'sender_vat_id',
                fieldLabel: FIELD_LABELS.sender_vat_id || 'USt-IdNr',
                error: 'USt-IdNr nicht validierbar (VIES)',
                severity: 'error',
            })
        }

        // USt-ID-Land stimmt nicht
        if (v.vat_country_match === false) {
            errors.push({
                field: 'sender_vat_id',
                fieldLabel: FIELD_LABELS.sender_vat_id || 'USt-IdNr',
                error: 'USt-IdNr-Land stimmt nicht überein',
                severity: 'error',
            })
        }

        // Low-Confidence Felder
        if (v.field_confidence) {
            for (const [field, confidence] of Object.entries(v.field_confidence)) {
                if (typeof confidence === 'number' && confidence < CONFIDENCE_THRESHOLD) {
                    if (!errors.some(e => e.field === field)) {
                        errors.push({
                            field,
                            fieldLabel: FIELD_LABELS[field] || field,
                            error: `Niedrige Konfidenz (${Math.round(confidence * 100)}%)`,
                            severity: 'error',
                        })
                    }
                }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 2. KRITISCHE PFLICHTFELDER (severity: error)
    // ═══════════════════════════════════════════════════════════════

    // Identifikation
    checkField('invoice_number', invoice.invoice_number, 'error', 'Pflichtfeld nicht erkannt')
    checkField('invoice_date', invoice.invoice_date, 'error', 'Pflichtfeld nicht erkannt')

    // Beträge
    checkField('gross_amount', invoice.gross_amount, 'error', 'Pflichtfeld nicht erkannt')

    // Absender Firma
    checkField('sender_company', invoice.sender?.company, 'error', 'Pflichtfeld nicht erkannt')

    // ═══════════════════════════════════════════════════════════════
    // 3. WICHTIGE FELDER (alle als Fehler)
    // ═══════════════════════════════════════════════════════════════

    // Absender-Adresse
    checkField('sender_street', invoice.sender?.street, 'error', 'Adresse unvollständig')
    checkField('sender_zip_code', invoice.sender?.zip_code, 'error', 'Adresse unvollständig')
    checkField('sender_city', invoice.sender?.city, 'error', 'Adresse unvollständig')

    // Beträge
    checkField('net_amount', invoice.net_amount, 'error', 'Betrag fehlt')
    checkField('vat_amount', invoice.vat_amount, 'error', 'MwSt fehlt')

    // Empfänger Firma
    checkField('recipient_company', invoice.recipient?.company, 'error', 'Empfänger fehlt')

    // ═══════════════════════════════════════════════════════════════
    // 4. EMPFÄNGER-DETAILS (alle als Fehler)
    // ═══════════════════════════════════════════════════════════════

    // Empfänger-Adresse Details
    checkField('recipient_street', invoice.recipient?.street, 'error', 'Straße fehlt')
    checkField('recipient_zip_code', invoice.recipient?.zip_code, 'error', 'PLZ fehlt')
    checkField('recipient_city', invoice.recipient?.city, 'error', 'Stadt fehlt')

    // Hausnummern
    checkField('sender_street_number', invoice.sender?.street_number, 'error', 'Hausnummer fehlt')
    checkField('recipient_street_number', invoice.recipient?.street_number, 'error', 'Hausnummer fehlt')

    // ═══════════════════════════════════════════════════════════════
    // 5. MATHEMATISCHE VALIDIERUNGEN (Konsistenz-Prüfungen)
    // ═══════════════════════════════════════════════════════════════

    const netAmount = typeof invoice.net_amount === 'number' ? invoice.net_amount : parseFloat(String(invoice.net_amount || '0'))
    const grossAmount = typeof invoice.gross_amount === 'number' ? invoice.gross_amount : parseFloat(String(invoice.gross_amount || '0'))
    const vatAmount = typeof invoice.vat_amount === 'number' ? invoice.vat_amount : parseFloat(String(invoice.vat_amount || '0'))

    // 5.1 NEGATIVE BETRÄGE (unmöglich!)
    if (netAmount < 0 && !errors.some(e => e.field === 'net_amount' && e.error.includes('negativ'))) {
        errors.push({
            field: 'net_amount',
            fieldLabel: 'Nettobetrag',
            error: `Negativer Betrag (${netAmount.toFixed(2)} EUR) - Extraktion fehlerhaft`,
            severity: 'error',
        })
    }
    if (grossAmount < 0 && !errors.some(e => e.field === 'gross_amount' && e.error.includes('negativ'))) {
        errors.push({
            field: 'gross_amount',
            fieldLabel: 'Bruttobetrag',
            error: `Negativer Betrag (${grossAmount.toFixed(2)} EUR) - Extraktion fehlerhaft`,
            severity: 'error',
        })
    }
    if (vatAmount < 0 && !errors.some(e => e.field === 'vat_amount' && e.error.includes('negativ'))) {
        errors.push({
            field: 'vat_amount',
            fieldLabel: 'MwSt-Betrag',
            error: `Negativer Betrag (${vatAmount.toFixed(2)} EUR) - Extraktion fehlerhaft`,
            severity: 'error',
        })
    }

    // 5.2 MwSt > BRUTTO (mathematisch unmöglich!)
    if (vatAmount > 0 && grossAmount > 0 && vatAmount > grossAmount) {
        errors.push({
            field: 'vat_amount',
            fieldLabel: 'MwSt-Betrag',
            error: `MwSt (${vatAmount.toFixed(2)}) größer als Brutto (${grossAmount.toFixed(2)}) - unmöglich!`,
            severity: 'error',
        })
    }

    // 5.3 MwSt > NETTO (verdächtig - normalerweise max ~20%)
    if (vatAmount > 0 && netAmount > 0 && vatAmount > netAmount) {
        errors.push({
            field: 'vat_amount',
            fieldLabel: 'MwSt-Betrag',
            error: `MwSt (${vatAmount.toFixed(2)}) größer als Netto (${netAmount.toFixed(2)}) - unplausibel`,
            severity: 'error',
        })
    }

    // 5.4 NETTO + MwSt != BRUTTO (Konsistenzfehler)
    if (netAmount > 0 && vatAmount >= 0 && grossAmount > 0) {
        const expectedGross = netAmount + vatAmount
        const diff = Math.abs(expectedGross - grossAmount)
        // Toleranz: 1% oder 2 EUR
        const tolerance = Math.max(grossAmount * 0.01, 2)
        if (diff > tolerance) {
            errors.push({
                field: 'gross_amount',
                fieldLabel: 'Bruttobetrag',
                error: `Netto (${netAmount.toFixed(2)}) + MwSt (${vatAmount.toFixed(2)}) = ${expectedGross.toFixed(2)}, aber Brutto ist ${grossAmount.toFixed(2)}`,
                severity: 'error',
            })
        }
    }

    // 5.5 REVERSE CHARGE MIT MwSt > 0 (Widerspruch!)
    if (invoice.is_reverse_charge && vatAmount > 0) {
        errors.push({
            field: 'vat_amount',
            fieldLabel: 'MwSt bei Reverse Charge',
            error: `Reverse Charge aktiv, aber MwSt = ${vatAmount.toFixed(2)} EUR (sollte 0 sein)`,
            severity: 'error',
        })
    }

    // ═══════════════════════════════════════════════════════════════
    // 6. DATENQUALITÄT (HTML, Sonderzeichen, etc.)
    // ═══════════════════════════════════════════════════════════════

    // 6.1 HTML-TAGS IN EXTRAHIERTEN DATEN
    const htmlTagPattern = /<[^>]+>/
    const checkForHtml = (field: string, value: string | null | undefined, label: string) => {
        if (value && htmlTagPattern.test(value)) {
            errors.push({
                field,
                fieldLabel: label,
                error: `HTML-Tags in Daten: "${value.substring(0, 50)}..."`,
                severity: 'error',
            })
        }
    }

    checkForHtml('sender_company', invoice.sender?.company, 'Absender Firma')
    checkForHtml('recipient_company', invoice.recipient?.company, 'Empfänger Firma')
    checkForHtml('sender_street', invoice.sender?.street, 'Absender Straße')
    checkForHtml('recipient_street', invoice.recipient?.street, 'Empfänger Straße')
    checkForHtml('invoice_number', invoice.invoice_number, 'Rechnungsnummer')

    // 6.2 UNREALISTISCH HOHE BETRAEGE (> 10 Mio EUR)
    const MAX_REALISTIC_AMOUNT = 10_000_000
    if (netAmount > MAX_REALISTIC_AMOUNT || grossAmount > MAX_REALISTIC_AMOUNT) {
        errors.push({
            field: 'gross_amount',
            fieldLabel: 'Betrag',
            error: `Unrealistisch hoher Betrag (${Math.max(netAmount, grossAmount).toLocaleString('de-DE')} EUR) - möglicherweise Lesefehler`,
            severity: 'error',
        })
    }

    // ═══════════════════════════════════════════════════════════════
    // 7. GESCHÄFTSLOGIK-VALIDIERUNGEN (Plausibilitätsprüfungen)
    // ═══════════════════════════════════════════════════════════════

    const senderCompany = invoice.sender?.company?.toLowerCase().trim() || ''
    const recipientCompany = invoice.recipient?.company?.toLowerCase().trim() || ''
    const senderCountry = invoice.sender?.country?.toUpperCase().trim() || ''
    const recipientCountry = invoice.recipient?.country?.toUpperCase().trim() || ''

    // 7.1 SELBST-RECHNUNG (Sender = Empfänger)
    if (senderCompany && recipientCompany) {
        // Normalisiere für Vergleich (entferne Rechtsform-Suffixe)
        const normalizeCompany = (name: string) => {
            return name
                .replace(/\s+(gmbh|ag|kg|ohg|gbr|ug|e\.?v\.?|bv|b\.?v\.?|ltd|inc|corp|llc|sa|sas|sarl|srl|spa|nv|n\.?v\.?)\.?$/i, '')
                .replace(/[^\w\s]/g, '')
                .replace(/\s+/g, ' ')
                .trim()
        }
        const normalizedSender = normalizeCompany(senderCompany)
        const normalizedRecipient = normalizeCompany(recipientCompany)

        // Prüfe auf ähnliche Namen (Selbst-Rechnung)
        if (normalizedSender && normalizedRecipient &&
            (normalizedSender === normalizedRecipient ||
             normalizedSender.includes(normalizedRecipient) ||
             normalizedRecipient.includes(normalizedSender))) {
            errors.push({
                field: 'recipient_company',
                fieldLabel: 'Selbst-Rechnung',
                error: `Absender und Empfänger scheinen identisch: "${invoice.sender?.company}" ↔ "${invoice.recipient?.company}"`,
                severity: 'error',
            })
        }
    }

    // 7.2 BANK ALS EMPFÄNGER (ungewöhnlich - normalerweise ist Bank der Zahlungsempfänger, nicht Rechnungsempfänger)
    const bankKeywords = ['bank', 'sparkasse', 'volksbank', 'raiffeisen', 'commerzbank', 'deutsche bank', 'unicredit', 'ing', 'dkb', 'postbank', 'landesbank', 'kreditinstitut', 'credit', 'finance', 'finanz']
    const recipientLower = (invoice.recipient?.company || '').toLowerCase()
    const isBankRecipient = bankKeywords.some(keyword => recipientLower.includes(keyword))

    if (isBankRecipient && !recipientLower.includes('bankverbindung')) {
        errors.push({
            field: 'recipient_company',
            fieldLabel: 'Empfänger',
            error: `Bank als Rechnungsempfänger: "${invoice.recipient?.company}" - Extraktion möglicherweise fehlerhaft`,
            severity: 'error',
        })
    }

    // 7.3 REVERSE CHARGE MIT DEUTSCHEM ABSENDER (Widerspruch!)
    // Reverse Charge gilt nur für EU-Lieferungen an Unternehmen, wenn Absender im Ausland ist
    if (invoice.is_reverse_charge && senderCountry === 'DE') {
        errors.push({
            field: 'is_reverse_charge',
            fieldLabel: 'Reverse Charge',
            error: `Reverse Charge aktiv, aber Absender ist deutsch (${senderCountry}) - Widerspruch!`,
            severity: 'error',
        })
    }

    // 7.4 AUSLÄNDISCHER ABSENDER OHNE REVERSE CHARGE
    // Bei Lieferungen aus EU-Ländern an deutsche Unternehmen sollte normalerweise Reverse Charge gelten
    const euCountries = ['AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE']
    const isForeignEuSender = senderCountry && senderCountry !== 'DE' && euCountries.includes(senderCountry)
    const isGermanRecipient = recipientCountry === 'DE' || (!recipientCountry && invoice.recipient?.city?.toLowerCase().match(/(berlin|münchen|hamburg|köln|frankfurt|stuttgart|düsseldorf|dortmund|essen|leipzig|bremen|dresden|hannover|nürnberg|duisburg)/))

    if (isForeignEuSender && !invoice.is_reverse_charge) {
        if (vatAmount === 0 && isGermanRecipient) {
            // Fall A: MwSt=0 aber kein RC markiert - wahrscheinlich RC vergessen
            errors.push({
                field: 'is_reverse_charge',
                fieldLabel: 'Reverse Charge',
                error: `Absender aus ${senderCountry}, Empfänger deutsch, MwSt=0 - Reverse Charge fehlt vermutlich`,
                severity: 'error',
            })
        } else if (vatAmount > 0) {
            // Fall B: EU-Absender berechnet MwSt - bei B2B sollte normalerweise RC gelten
            errors.push({
                field: 'is_reverse_charge',
                fieldLabel: 'Reverse Charge',
                error: `EU-Absender (${senderCountry}) berechnet ${vatAmount.toFixed(2)} EUR MwSt - bei B2B sollte RC gelten`,
                severity: 'error',
            })
        }
    }

    // 7.5 NETTO > BRUTTO (mathematisch unmöglich!)
    if (netAmount > 0 && grossAmount > 0 && netAmount > grossAmount) {
        // Nur wenn nicht schon ein anderer Betragsfehler gemeldet wurde
        if (!errors.some(e => e.field === 'net_amount' && e.error.includes('größer'))) {
            errors.push({
                field: 'net_amount',
                fieldLabel: 'Nettobetrag',
                error: `Netto (${netAmount.toFixed(2)}) größer als Brutto (${grossAmount.toFixed(2)}) - unmöglich!`,
                severity: 'error',
            })
        }
    }

    // 7.6 DOPPELTE RECHNUNGSNUMMERN-WARNUNG (Info aus Metadaten falls vorhanden)
    // Note: Echte Duplikat-Erkennung muss im Backend erfolgen, hier nur Hinweis wenn invoice_number verdächtig aussieht
    const invoiceNumber = invoice.invoice_number || ''
    if (invoiceNumber.match(/^(test|demo|example|muster|probe)/i)) {
        errors.push({
            field: 'invoice_number',
            fieldLabel: 'Rechnungsnummer',
            error: `Verdächtige Rechnungsnummer: "${invoiceNumber}" - möglicherweise Testdokument`,
            severity: 'error',
        })
    }

    // 7.7 MwSt = BRUTTO (100% MwSt unmöglich!)
    if (vatAmount > 0 && grossAmount > 0 && Math.abs(vatAmount - grossAmount) < 0.01) {
        errors.push({
            field: 'vat_amount',
            fieldLabel: 'MwSt-Betrag',
            error: `MwSt (${vatAmount.toFixed(2)}) = Brutto (${grossAmount.toFixed(2)}) - 100% MwSt unmöglich!`,
            severity: 'error',
        })
    }

    // 7.8 WEDER SENDER NOCH EMPFÄNGER (komplett unbrauchbar)
    if (!invoice.sender?.company && !invoice.recipient?.company) {
        errors.push({
            field: 'sender_company',
            fieldLabel: 'Parteien',
            error: 'Weder Absender noch Empfänger erkannt - Extraktion fehlgeschlagen',
            severity: 'error',
        })
    }

    // 7.9 MwSt-SATZ STIMMT NICHT MIT BETRAEGEN
    if (netAmount > 0 && vatAmount > 0 && invoice.vat_rate) {
        const declaredRate = typeof invoice.vat_rate === 'number' ? invoice.vat_rate : parseFloat(String(invoice.vat_rate))
        if (!isNaN(declaredRate) && declaredRate > 0) {
            const expectedVat = netAmount * (declaredRate / 100)
            const actualVatRate = (vatAmount / netAmount) * 100
            // Toleranz: +/- 5 Prozentpunkte UND 50% relative Abweichung
            const rateDiff = Math.abs(actualVatRate - declaredRate)
            const absoluteDiff = Math.abs(vatAmount - expectedVat)
            if (rateDiff > 5 && absoluteDiff / Math.max(expectedVat, 1) > 0.5) {
                errors.push({
                    field: 'vat_rate',
                    fieldLabel: 'MwSt-Satz',
                    error: `MwSt-Satz ${declaredRate}% ergibt ${expectedVat.toFixed(2)} EUR, aber MwSt = ${vatAmount.toFixed(2)} EUR (${actualVatRate.toFixed(0)}%)`,
                    severity: 'error',
                })
            }
        }
    }

    // 7.10 MwSt LEER ABER NICHT NULL (fehlende Extraktion)
    // Prüfe ob MwSt fehlt aber aufgrund der Beträge vorhanden sein sollte
    const vatMissing = invoice.vat_amount === undefined || invoice.vat_amount === null ||
                       (typeof invoice.vat_amount === 'string' && (invoice.vat_amount as unknown as string).trim() === '')
    if (vatMissing && netAmount > 0 && grossAmount > netAmount) {
        errors.push({
            field: 'vat_amount',
            fieldLabel: 'MwSt-Betrag',
            error: `MwSt-Feld leer, aber Brutto (${grossAmount.toFixed(2)}) > Netto (${netAmount.toFixed(2)}) - MwSt fehlt`,
            severity: 'error',
        })
    }

    // 7.11 EMPFÄNGER NUR RECHTSFORM (kein vollständiger Firmenname)
    const legalFormOnlyPattern = /^(gmbh|ag|kg|ohg|gbr|ug|e\.?v\.?|bv|b\.?v\.?|ltd|inc|corp|llc|sa|sas|sarl|srl|spa|nv|n\.?v\.?|co\.?\s*kg|gmbh\s*&?\s*co\.?\s*kg)\.?$/i
    if (invoice.recipient?.company && legalFormOnlyPattern.test(invoice.recipient.company.trim())) {
        errors.push({
            field: 'recipient_company',
            fieldLabel: 'Empfänger',
            error: `Nur Rechtsform erkannt: "${invoice.recipient.company}" - vollständiger Firmenname fehlt`,
            severity: 'error',
        })
    }
    // Auch für Absender prüfen
    if (invoice.sender?.company && legalFormOnlyPattern.test(invoice.sender.company.trim())) {
        errors.push({
            field: 'sender_company',
            fieldLabel: 'Absender',
            error: `Nur Rechtsform erkannt: "${invoice.sender.company}" - vollständiger Firmenname fehlt`,
            severity: 'error',
        })
    }

    // 7.12 MwSt = NETTO (100% MwSt auf Netto unmöglich!)
    if (vatAmount > 0 && netAmount > 0 && Math.abs(vatAmount - netAmount) < 0.01) {
        errors.push({
            field: 'vat_amount',
            fieldLabel: 'MwSt-Betrag',
            error: `MwSt (${vatAmount.toFixed(2)}) = Netto (${netAmount.toFixed(2)}) - 100% MwSt unmöglich!`,
            severity: 'error',
        })
    }

    // 7.13 RATE=0 ABER MwSt VORHANDEN (Widerspruch)
    const declaredRateForZeroCheck = typeof invoice.vat_rate === 'number' ? invoice.vat_rate : parseFloat(String(invoice.vat_rate || ''))
    if (declaredRateForZeroCheck === 0 && vatAmount > 0.01) {
        errors.push({
            field: 'vat_rate',
            fieldLabel: 'MwSt-Satz',
            error: `MwSt-Satz = 0% aber MwSt = ${vatAmount.toFixed(2)} EUR - Widerspruch!`,
            severity: 'error',
        })
    }

    return errors
}

/**
 * Berechnet Flag-Gründe aus QueueItem und ExtractedData.
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

    // Coverage-Lücke
    if (reasonParts.some(r => r.includes('Coverage-Lücke'))) {
        const match = queueItem.reason.match(/Coverage-Lücke \((\d+)%\)/)
        const coverage = match ? match[1] : '?'
        reasons.push({
            type: 'coverage_gap',
            label: 'Coverage-Lücke',
            details: `Coverage für "${queueItem.document_type}" bei ${coverage}% (Ziel: 90%)`,
            severity: 'critical',
        })
    }

    // Stichproben-Review
    if (queueItem.is_spot_check) {
        reasons.push({
            type: 'spot_check',
            label: 'Stichprobe',
            details: 'Zufällig ausgewählte Stichprobe aus Auto-Accepted Samples',
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

    // Geschäftskritisch (Rechnung)
    if (reasonParts.some(r => r.includes('Geschäftskritisch'))) {
        reasons.push({
            type: 'business_critical',
            label: 'Geschäftskritisch',
            details: 'Rechnung - erhöhte Priorität für Buchhaltung',
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

    // Low-Confidence Felder hinzufügen wenn nicht schon erfasst
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
 * Hook um ExtractedDocumentData für Review zu laden.
 *
 * NEU: Nutzt extracted_data direkt aus QueueItem wenn vorhanden,
 * fällt zurück auf API-Call wenn document_id existiert.
 */
export function useExtractedDataForReview(
    documentId: string | null | undefined,
    queueItem: QueueItem | null | undefined
) {
    // Prüfe ob extracted_data direkt im QueueItem vorhanden ist
    const hasInlineData = !!queueItem?.extracted_data

    // Query für ExtractedData - nur wenn keine Inline-Daten UND document_id existiert
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

    // Confidence-Map für schnellen Zugriff
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
