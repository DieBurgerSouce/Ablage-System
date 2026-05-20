/**
 * PaymentTermsSection - Editierbare Zahlungsbedingungen.
 */

import { Calendar } from 'lucide-react'
import { EditableField } from '../EditableField'
import type { ExtractedInvoiceData } from '@/features/extracted-data/types/extracted-data.types'
import type { UseFieldCorrectionsReturn } from '../../hooks/use-field-corrections'
import type { UseExtractedDataForReviewReturn } from '../../hooks/use-extracted-data-review'

interface PaymentTermsSectionProps {
    invoice: ExtractedInvoiceData
    corrections: UseFieldCorrectionsReturn
    extractedDataReview: UseExtractedDataForReviewReturn
    disabled?: boolean
    className?: string
}

export function PaymentTermsSection({
    invoice,
    corrections,
    extractedDataReview,
    disabled = false,
    className,
}: PaymentTermsSectionProps) {
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

    // Helper für Feld-Props
    const getFieldProps = (field: string, value: string | number | null | undefined) => {
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

    return (
        <div className={className}>
            {/* Section Header - kompakt */}
            <div className="flex items-center gap-1.5 mb-2">
                <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Zahlung
                </span>
            </div>

            <div className="grid grid-cols-2 gap-2">
                {/* Zahlungsfrist */}
                <EditableField
                    fieldPath="payment_terms_days"
                    fieldLabel="Frist (Tage)"
                    type="number"
                    {...getFieldProps('payment_terms_days', invoice.payment_terms_days)}
                />

                {/* Skonto */}
                <EditableField
                    fieldPath="discount_percent"
                    fieldLabel="Skonto %"
                    type="number"
                    {...getFieldProps('discount_percent', invoice.discount_percent)}
                />
            </div>
        </div>
    )
}
