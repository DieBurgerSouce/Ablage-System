/**
 * IdentificationSection - Editierbare Rechnungs-Identifikation.
 *
 * Felder: Rechnungsnummer, Datum, Fälligkeitsdatum, Bestellnummer, etc.
 */

import { Hash, ArrowDownLeft, ArrowUpRight, HelpCircle } from 'lucide-react'
import { EditableField } from '../EditableField'
import { cn } from '@/lib/utils'
import type { ExtractedInvoiceData } from '@/features/extracted-data/types/extracted-data.types'
import type { UseFieldCorrectionsReturn } from '../../hooks/use-field-corrections'
import type { UseExtractedDataForReviewReturn } from '../../hooks/use-extracted-data-review'

interface IdentificationSectionProps {
    invoice: ExtractedInvoiceData
    corrections: UseFieldCorrectionsReturn
    extractedDataReview: UseExtractedDataForReviewReturn
    disabled?: boolean
    className?: string
}

export function IdentificationSection({
    invoice,
    corrections,
    extractedDataReview,
    disabled = false,
    className,
}: IdentificationSectionProps) {
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

    // Hat zusätzliche Referenzen?
    const hasAdditionalRefs = !!(
        invoice.order_number ||
        invoice.delivery_note_number ||
        invoice.customer_number ||
        invoice.supplier_number
    )

    // Hat Leistungszeitraum?
    const hasServicePeriod = !!(invoice.service_period_start || invoice.service_period_end)

    // Invoice Direction Helper
    const getDirectionDisplay = () => {
        const direction = invoice.invoice_direction
        const confidence = invoice.invoice_direction_confidence
        const reason = invoice.invoice_direction_reason

        if (!direction || direction === 'unknown') {
            return {
                label: 'Rechnung',
                sublabel: 'Typ unbekannt',
                icon: HelpCircle,
                bgClass: 'bg-muted/50',
                textClass: 'text-muted-foreground',
                borderClass: 'border-muted-foreground/30',
            }
        }

        if (direction === 'incoming') {
            return {
                label: 'Eingangsrechnung',
                sublabel: reason || 'Empfänger = Eigene Firma',
                icon: ArrowDownLeft,
                bgClass: 'bg-blue-500/10',
                textClass: 'text-blue-600 dark:text-blue-400',
                borderClass: 'border-blue-500/30',
                confidence,
            }
        }

        // outgoing
        return {
            label: 'Ausgangsrechnung',
            sublabel: reason || 'Absender = Eigene Firma',
            icon: ArrowUpRight,
            bgClass: 'bg-green-500/10',
            textClass: 'text-green-600 dark:text-green-400',
            borderClass: 'border-green-500/30',
            confidence,
        }
    }

    const directionInfo = getDirectionDisplay()
    const DirectionIcon = directionInfo.icon

    return (
        <div className={className}>
            {/* Invoice Direction Badge - prominent */}
            <div className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-lg border mb-3',
                directionInfo.bgClass,
                directionInfo.borderClass
            )}>
                <DirectionIcon className={cn('h-5 w-5', directionInfo.textClass)} />
                <div className="flex-1 min-w-0">
                    <span className={cn('font-semibold text-sm', directionInfo.textClass)}>
                        {directionInfo.label}
                    </span>
                    {directionInfo.sublabel && (
                        <p className="text-xs text-muted-foreground truncate">
                            {directionInfo.sublabel}
                        </p>
                    )}
                </div>
                {directionInfo.confidence !== undefined && directionInfo.confidence > 0 && (
                    <span className="text-xs text-muted-foreground">
                        {Math.round(directionInfo.confidence * 100)}%
                    </span>
                )}
            </div>

            {/* Section Header - kompakt */}
            <div className="flex items-center gap-1.5 mb-2">
                <Hash className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Identifikation
                </span>
            </div>

            {/* Hauptfelder - kompaktes Grid */}
            <div className="grid grid-cols-2 gap-2">
                <EditableField
                    fieldPath="invoice_number"
                    fieldLabel="Re.-Nr."
                    {...getFieldProps('invoice_number', invoice.invoice_number)}
                />
                <EditableField
                    fieldPath="invoice_date"
                    fieldLabel="Datum"
                    type="date"
                    {...getFieldProps('invoice_date', invoice.invoice_date)}
                />
                <EditableField
                    fieldPath="due_date"
                    fieldLabel="Fällig"
                    type="date"
                    {...getFieldProps('due_date', invoice.due_date)}
                />
                {invoice.discount_due_date && (
                    <EditableField
                        fieldPath="discount_due_date"
                        fieldLabel="Skonto"
                        type="date"
                        {...getFieldProps('discount_due_date', invoice.discount_due_date)}
                    />
                )}
            </div>

            {/* Zusätzliche Referenzen - nur wenn vorhanden */}
            {hasAdditionalRefs && (
                <div className="grid grid-cols-2 gap-2 mt-2 pt-2 border-t border-border/30">
                    {invoice.order_number !== undefined && invoice.order_number && (
                        <EditableField
                            fieldPath="order_number"
                            fieldLabel="Bestellung"
                            {...getFieldProps('order_number', invoice.order_number)}
                        />
                    )}
                    {invoice.delivery_note_number !== undefined && invoice.delivery_note_number && (
                        <EditableField
                            fieldPath="delivery_note_number"
                            fieldLabel="Lieferschein"
                            {...getFieldProps('delivery_note_number', invoice.delivery_note_number)}
                        />
                    )}
                    {invoice.customer_number !== undefined && invoice.customer_number && (
                        <EditableField
                            fieldPath="customer_number"
                            fieldLabel="Kunde"
                            {...getFieldProps('customer_number', invoice.customer_number)}
                        />
                    )}
                    {invoice.supplier_number !== undefined && invoice.supplier_number && (
                        <EditableField
                            fieldPath="supplier_number"
                            fieldLabel="Lieferant"
                            {...getFieldProps('supplier_number', invoice.supplier_number)}
                        />
                    )}
                </div>
            )}

            {/* Leistungszeitraum - kompakt */}
            {hasServicePeriod && (
                <div className="flex items-center gap-2 mt-2 pt-2 border-t border-border/30">
                    <span className="text-xs text-muted-foreground">Zeitraum:</span>
                    <EditableField
                        fieldPath="service_period_start"
                        fieldLabel=""
                        type="date"
                        placeholder="Von"
                        className="flex-1"
                        {...getFieldProps('service_period_start', invoice.service_period_start)}
                    />
                    <span className="text-muted-foreground text-xs">-</span>
                    <EditableField
                        fieldPath="service_period_end"
                        fieldLabel=""
                        type="date"
                        placeholder="Bis"
                        className="flex-1"
                        {...getFieldProps('service_period_end', invoice.service_period_end)}
                    />
                </div>
            )}
        </div>
    )
}
