/**
 * StructuredReviewPanel - Container für strukturierte Daten-Review.
 *
 * Orchestriert alle editierbaren Sektionen und zeigt:
 * - Flag-Gründe
 * - Validierungsfehler
 * - Dokumenttyp-spezifische Sektionen (Invoice, Order, Contract)
 */

import { FileText, AlertCircle } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'

// FlagReasonBanner und ValidationAlerts werden später integriert
import {
    IdentificationSection,
    AddressSection,
    AmountsSection,
    BankAccountSection,
    PaymentTermsSection,
} from './editable'

import type { QueueItem } from '../types'
import type { UseExtractedDataForReviewReturn } from '../hooks/use-extracted-data-review'
import type { UseFieldCorrectionsReturn } from '../hooks/use-field-corrections'

interface StructuredReviewPanelProps {
    queueItem: QueueItem | null | undefined
    extractedDataReview: UseExtractedDataForReviewReturn
    corrections: UseFieldCorrectionsReturn
    disabled?: boolean
    className?: string
}

export function StructuredReviewPanel({
    queueItem,
    extractedDataReview,
    corrections,
    disabled = false,
    className,
}: StructuredReviewPanelProps) {
    const {
        invoiceData,
        orderData,
        contractData,
        validationErrors,
        isLoading,
        error,
        hasExtractedData,
        documentType,
    } = extractedDataReview

    // Loading State
    if (isLoading) {
        return (
            <div className={`space-y-4 ${className}`}>
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-24 w-full" />
                <div className="grid grid-cols-2 gap-4">
                    <Skeleton className="h-32" />
                    <Skeleton className="h-32" />
                </div>
                <Skeleton className="h-24 w-full" />
            </div>
        )
    }

    // Keine extracted_data UND keine document_id -> keine Daten verfügbar
    if (!queueItem?.extracted_data && !queueItem?.document_id) {
        return (
            <Alert className={className}>
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Keine strukturierten Daten</AlertTitle>
                <AlertDescription>
                    Für dieses Sample sind keine strukturierten Daten verfügbar.
                    Bitte nutzen Sie den OCR-Text Tab für die Korrektur.
                </AlertDescription>
            </Alert>
        )
    }

    if (error) {
        return (
            <Alert variant="destructive" className={className}>
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Fehler beim Laden</AlertTitle>
                <AlertDescription>
                    {error instanceof Error ? error.message : 'Unbekannter Fehler beim Laden der extrahierten Daten.'}
                </AlertDescription>
            </Alert>
        )
    }

    if (!hasExtractedData) {
        return (
            <Alert className={className}>
                <FileText className="h-4 w-4" />
                <AlertTitle>Keine extrahierten Daten</AlertTitle>
                <AlertDescription>
                    Für dieses Dokument wurden keine strukturierten Daten extrahiert.
                    Möglicherweise wurde das Dokument vor der Einführung der Strukturextraktion verarbeitet.
                </AlertDescription>
            </Alert>
        )
    }

    // Render basierend auf Dokumenttyp
    return (
        <ScrollArea className={`h-full ${className}`}>
            <div className="space-y-3 pr-3">
                {/* Validierungs-Anzeige - Nur Fehler */}
                {validationErrors.length > 0 && (
                    <div className="pb-3 border-b border-border/50 space-y-2">
                        {/* Fehler-Badge */}
                        <span className="inline-flex items-center text-sm font-bold px-3 py-1.5 rounded bg-red-500 text-black">
                            {validationErrors.length} {validationErrors.length === 1 ? 'Fehler' : 'Fehler'}
                        </span>

                        {/* Fehler-Liste */}
                        <ul className="text-xs space-y-0.5">
                            {validationErrors.map((err, i) => (
                                <li key={`error-${i}`} className="flex items-start gap-1.5 text-red-400">
                                    <span className="text-red-500 mt-0.5 font-bold">✕</span>
                                    <span><strong>{err.fieldLabel}:</strong> {err.error}</span>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {/* Dokumenttyp-spezifische Sektionen */}
                {documentType === 'invoice' && invoiceData && (
                    <InvoiceSections
                        invoice={invoiceData}
                        corrections={corrections}
                        extractedDataReview={extractedDataReview}
                        disabled={disabled}
                    />
                )}

                {documentType === 'order' && orderData && (
                    <OrderSections
                        order={orderData}
                        corrections={corrections}
                        extractedDataReview={extractedDataReview}
                        disabled={disabled}
                    />
                )}

                {documentType === 'contract' && contractData && (
                    <ContractSections
                        contract={contractData}
                        corrections={corrections}
                        extractedDataReview={extractedDataReview}
                        disabled={disabled}
                    />
                )}

                {/* Fallback für unbekannte Typen */}
                {!['invoice', 'order', 'contract'].includes(documentType || '') && (
                    <Alert>
                        <FileText className="h-4 w-4" />
                        <AlertTitle>Dokumenttyp: {documentType || 'Unbekannt'}</AlertTitle>
                        <AlertDescription>
                            Für diesen Dokumenttyp ist noch keine strukturierte Ansicht verfügbar.
                            Bitte nutzen Sie den OCR-Text Tab.
                        </AlertDescription>
                    </Alert>
                )}
            </div>
        </ScrollArea>
    )
}

// =============================================================================
// Dokumenttyp-spezifische Sektionen
// =============================================================================

interface InvoiceSectionsProps {
    invoice: NonNullable<UseExtractedDataForReviewReturn['invoiceData']>
    corrections: UseFieldCorrectionsReturn
    extractedDataReview: UseExtractedDataForReviewReturn
    disabled: boolean
}

function InvoiceSections({ invoice, corrections, extractedDataReview, disabled }: InvoiceSectionsProps) {
    return (
        <>
            {/* Identifikation */}
            <IdentificationSection
                invoice={invoice}
                corrections={corrections}
                extractedDataReview={extractedDataReview}
                disabled={disabled}
            />

            {/* Adressen */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <AddressSection
                    title="Absender"
                    address={invoice.sender}
                    prefix="sender"
                    vatId={invoice.sender_vat_id}
                    taxNumber={invoice.sender_tax_number}
                    corrections={corrections}
                    extractedDataReview={extractedDataReview}
                    disabled={disabled}
                />
                <AddressSection
                    title="Empfänger"
                    address={invoice.recipient}
                    prefix="recipient"
                    vatId={invoice.recipient_vat_id}
                    corrections={corrections}
                    extractedDataReview={extractedDataReview}
                    disabled={disabled}
                />
            </div>

            {/* Beträge */}
            <AmountsSection
                invoice={invoice}
                corrections={corrections}
                extractedDataReview={extractedDataReview}
                disabled={disabled}
            />

            {/* Zahlungsbedingungen */}
            <PaymentTermsSection
                invoice={invoice}
                corrections={corrections}
                extractedDataReview={extractedDataReview}
                disabled={disabled}
            />

            {/* Bankverbindung */}
            <BankAccountSection
                bank={invoice.sender_bank}
                validations={invoice.validations}
                corrections={corrections}
                extractedDataReview={extractedDataReview}
                disabled={disabled}
            />
        </>
    )
}

interface OrderSectionsProps {
    order: NonNullable<UseExtractedDataForReviewReturn['orderData']>
    corrections: UseFieldCorrectionsReturn
    extractedDataReview: UseExtractedDataForReviewReturn
    disabled: boolean
}

function OrderSections({ order: _order, corrections: _corrections, extractedDataReview: _extractedDataReview, disabled: _disabled }: OrderSectionsProps) {
    // TODO: Implement Order-spezifische Sektionen
    // Für jetzt zeigen wir eine Placeholder-Nachricht
    return (
        <Alert>
            <FileText className="h-4 w-4" />
            <AlertTitle>Bestellung erkannt</AlertTitle>
            <AlertDescription>
                Die strukturierte Bearbeitungsansicht für Bestellungen wird in Kürze verfügbar sein.
                Bitte nutzen Sie vorerst den OCR-Text Tab.
            </AlertDescription>
        </Alert>
    )
}

interface ContractSectionsProps {
    contract: NonNullable<UseExtractedDataForReviewReturn['contractData']>
    corrections: UseFieldCorrectionsReturn
    extractedDataReview: UseExtractedDataForReviewReturn
    disabled: boolean
}

function ContractSections({ contract: _contract, corrections: _corrections, extractedDataReview: _extractedDataReview, disabled: _disabled }: ContractSectionsProps) {
    // TODO: Implement Contract-spezifische Sektionen
    // Für jetzt zeigen wir eine Placeholder-Nachricht
    return (
        <Alert>
            <FileText className="h-4 w-4" />
            <AlertTitle>Vertrag erkannt</AlertTitle>
            <AlertDescription>
                Die strukturierte Bearbeitungsansicht für Verträge wird in Kürze verfügbar sein.
                Bitte nutzen Sie vorerst den OCR-Text Tab.
            </AlertDescription>
        </Alert>
    )
}
