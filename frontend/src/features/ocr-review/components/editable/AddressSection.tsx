/**
 * AddressSection - Editierbare Adress-Anzeige.
 *
 * Verwendet für Absender und Empfänger.
 */

import { Building, User } from 'lucide-react'
import { EditableField } from '../EditableField'
import type { ExtractedAddress } from '@/features/extracted-data/types/extracted-data.types'
import type { UseFieldCorrectionsReturn } from '../../hooks/use-field-corrections'
import type { UseExtractedDataForReviewReturn } from '../../hooks/use-extracted-data-review'

interface AddressSectionProps {
    title: 'Absender' | 'Empfänger'
    address: ExtractedAddress | null | undefined
    prefix: 'sender' | 'recipient'
    vatId?: string
    corrections: UseFieldCorrectionsReturn
    extractedDataReview: UseExtractedDataForReviewReturn
    disabled?: boolean
    className?: string
}

export function AddressSection({
    title,
    address,
    prefix,
    vatId,
    corrections,
    extractedDataReview,
    disabled = false,
    className,
}: AddressSectionProps) {
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
    const getFieldProps = (fieldSuffix: string, value: string | null | undefined) => {
        const field = `${prefix}_${fieldSuffix}`
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

    return (
        <div className={className}>
            {/* Section Header - kompakt */}
            <div className="flex items-center gap-1.5 mb-2">
                {title === 'Absender' ? (
                    <Building className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                    <User className="h-3.5 w-3.5 text-muted-foreground" />
                )}
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {title}
                </span>
            </div>

            <div className="space-y-1.5">
                {/* Firma */}
                <EditableField
                    fieldPath={`${prefix}_company`}
                    fieldLabel="Firma"
                    {...getFieldProps('company', address?.company)}
                />

                {/* Straße + Nr kompakt */}
                <div className="grid grid-cols-4 gap-1.5">
                    <div className="col-span-3">
                        <EditableField
                            fieldPath={`${prefix}_street`}
                            fieldLabel="Straße"
                            {...getFieldProps('street', address?.street)}
                        />
                    </div>
                    <EditableField
                        fieldPath={`${prefix}_street_number`}
                        fieldLabel="Nr"
                        {...getFieldProps('street_number', address?.street_number)}
                    />
                </div>

                {/* PLZ / Stadt kompakt */}
                <div className="grid grid-cols-3 gap-1.5">
                    <EditableField
                        fieldPath={`${prefix}_zip_code`}
                        fieldLabel="PLZ"
                        {...getFieldProps('zip_code', address?.zip_code)}
                    />
                    <div className="col-span-2">
                        <EditableField
                            fieldPath={`${prefix}_city`}
                            fieldLabel="Ort"
                            {...getFieldProps('city', address?.city)}
                        />
                    </div>
                </div>

                {/* USt-IdNr */}
                <EditableField
                    fieldPath={`${prefix}_vat_id`}
                    fieldLabel="USt-IdNr"
                    {...getFieldProps('vat_id', vatId)}
                />
            </div>
        </div>
    )
}
