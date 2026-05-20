/**
 * AmountsSection - Editierbare Beträge mit Summen-Validierung.
 *
 * Zeigt Netto, MwSt, Brutto und Validierungsstatus.
 */

import { CreditCard, XCircle } from 'lucide-react'
import { EditableField } from '../EditableField'
import type { ExtractedInvoiceData } from '@/features/extracted-data/types/extracted-data.types'
import type { UseFieldCorrectionsReturn } from '../../hooks/use-field-corrections'
import type { UseExtractedDataForReviewReturn } from '../../hooks/use-extracted-data-review'

interface AmountsSectionProps {
    invoice: ExtractedInvoiceData
    corrections: UseFieldCorrectionsReturn
    extractedDataReview: UseExtractedDataForReviewReturn
    disabled?: boolean
    className?: string
}

export function AmountsSection({
    invoice,
    corrections,
    extractedDataReview,
    disabled = false,
    className,
}: AmountsSectionProps) {
    const {
        setCorrection,
        confirmField,
        unconfirmField,
        isFieldConfirmed,
        isFieldCorrected,
        getCorrection,
    } = corrections

    const {
        getFieldConfidence,
        hasValidationError,
        getValidationError,
    } = extractedDataReview

    // Validierung
    const validations = invoice.validations
    const sumsMatch = validations?.sums_match
    const sumsDifference = validations?.sums_difference

    // Helper für Feld-Props
    const getFieldProps = (field: string, value: number | string | null | undefined) => {
        const correction = getCorrection(field)
        const validationError = getValidationError(field)
        const normalizedValue = value ?? null // Convert undefined to null

        return {
            value: correction ? correction.correctedValue : value,
            confidence: getFieldConfidence(field),
            hasValidationError: hasValidationError(field),
            validationErrorMessage: validationError?.error,
            isConfirmed: isFieldConfirmed(field),
            isCorrected: isFieldCorrected(field),
            disabled,
            onEdit: (newValue: string) => setCorrection(field, normalizedValue, newValue),
            onConfirm: () => confirmField(field),
            onUnconfirm: () => unconfirmField(field),
        }
    }

    const currency = invoice.currency || 'EUR'

    return (
        <div className={className}>
            {/* Section Header - kompakt */}
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                    <CreditCard className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Beträge
                    </span>
                </div>
                {/* Summen-Fehler nur als kleiner Indikator */}
                {sumsMatch === false && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400">
                        Summen-Fehler
                    </span>
                )}
            </div>

            {/* Hauptbeträge - kompaktes Grid */}
            <div className="grid grid-cols-2 gap-2">
                <EditableField
                    fieldPath="net_amount"
                    fieldLabel="Netto"
                    type="currency"
                    {...getFieldProps('net_amount', invoice.net_amount)}
                />
                <EditableField
                    fieldPath="gross_amount"
                    fieldLabel="Brutto"
                    type="currency"
                    {...getFieldProps('gross_amount', invoice.gross_amount)}
                />
                <EditableField
                    fieldPath="vat_amount"
                    fieldLabel={`MwSt${invoice.vat_rate ? ` ${invoice.vat_rate}%` : ''}`}
                    type="currency"
                    {...getFieldProps('vat_amount', invoice.vat_amount)}
                />
                <EditableField
                    fieldPath="vat_rate"
                    fieldLabel="MwSt-%"
                    type="number"
                    {...getFieldProps('vat_rate', invoice.vat_rate)}
                />
            </div>

            {/* Summen-Differenz Warnung - kompakt */}
            {sumsMatch === false && sumsDifference !== undefined && sumsDifference !== null && (
                <p className="text-[10px] text-red-500 mt-1.5 flex items-center gap-1">
                    <XCircle className="h-3 w-3" />
                    Positionssumme weicht um {new Intl.NumberFormat('de-DE', { style: 'currency', currency }).format(sumsDifference)} vom Netto ab
                </p>
            )}

            {/* Reverse Charge - nur kleiner Hinweis */}
            {invoice.is_reverse_charge && (
                <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-1.5">
                    Reverse Charge
                </p>
            )}
        </div>
    )
}
