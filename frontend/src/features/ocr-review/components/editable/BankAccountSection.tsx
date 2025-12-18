/**
 * BankAccountSection - Editierbare Bankverbindung mit IBAN-Validierung.
 */

import { Building } from 'lucide-react'
import { EditableField } from '../EditableField'
import type { ExtractedBankAccount } from '@/features/extracted-data/types/extracted-data.types'
import type { UseFieldCorrectionsReturn } from '../../hooks/use-field-corrections'
import type { UseExtractedDataForReviewReturn } from '../../hooks/use-extracted-data-review'

interface BankAccountSectionProps {
    bank: ExtractedBankAccount | null | undefined
    validations?: {
        iban_checksum_valid?: boolean
        iban_country_match?: boolean
    }
    corrections: UseFieldCorrectionsReturn
    extractedDataReview: UseExtractedDataForReviewReturn
    disabled?: boolean
    className?: string
}

export function BankAccountSection({
    bank,
    validations,
    corrections,
    extractedDataReview,
    disabled = false,
    className,
}: BankAccountSectionProps) {
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
    const getFieldProps = (field: string, value: string | null | undefined) => {
        const correction = getCorrection(field)
        const validationError = getValidationError(field)
        const normalizedValue = value ?? null // Convert undefined to null

        return {
            value: correction ? String(correction.correctedValue) : value,
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

    // IBAN-Validierung
    const ibanValid = validations?.iban_checksum_valid

    return (
        <div className={className}>
            {/* Section Header - kompakt */}
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                    <Building className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Bank
                    </span>
                </div>
                {/* IBAN-Fehler nur als kleiner Indikator */}
                {ibanValid === false && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400">
                        IBAN ungültig
                    </span>
                )}
            </div>

            <div className="space-y-1.5">
                {/* IBAN */}
                <EditableField
                    fieldPath="sender_iban"
                    fieldLabel="IBAN"
                    {...getFieldProps('sender_iban', bank?.iban)}
                />

                {/* BIC */}
                <EditableField
                    fieldPath="sender_bic"
                    fieldLabel="BIC"
                    {...getFieldProps('sender_bic', bank?.bic)}
                />
            </div>
        </div>
    )
}
