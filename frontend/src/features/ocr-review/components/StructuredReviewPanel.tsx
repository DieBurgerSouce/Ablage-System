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
import { EditableField } from '../EditableField'

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

function OrderSections({ order, corrections, extractedDataReview, disabled }: OrderSectionsProps) {
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
        const normalizedValue = value ?? null

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
        <>
            {/* Bestellidentifikation */}
            <section className="space-y-3 pb-4 border-b border-border/50">
                <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    Bestellidentifikation
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <EditableField
                        fieldPath="order_number"
                        fieldLabel="Bestellnummer"
                        type="text"
                        {...getFieldProps('order_number', order.order_number)}
                    />
                    <EditableField
                        fieldPath="customer_order_number"
                        fieldLabel="Kundenbestellnummer"
                        type="text"
                        {...getFieldProps('customer_order_number', order.customer_order_number)}
                    />
                    {order.quotation_number && (
                        <EditableField
                            fieldPath="quotation_number"
                            fieldLabel="Angebotsnummer"
                            type="text"
                            {...getFieldProps('quotation_number', order.quotation_number)}
                        />
                    )}
                </div>
            </section>

            {/* Datum */}
            <section className="space-y-3 pb-4 border-b border-border/50">
                <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    Datum
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <EditableField
                        fieldPath="order_date"
                        fieldLabel="Bestelldatum"
                        type="date"
                        {...getFieldProps('order_date', order.order_date)}
                    />
                    <EditableField
                        fieldPath="delivery_date"
                        fieldLabel="Lieferdatum"
                        type="date"
                        {...getFieldProps('delivery_date', order.delivery_date)}
                    />
                    {order.confirmation_date && (
                        <EditableField
                            fieldPath="confirmation_date"
                            fieldLabel="Bestätigungsdatum"
                            type="date"
                            {...getFieldProps('confirmation_date', order.confirmation_date)}
                        />
                    )}
                    {order.validity_date && (
                        <EditableField
                            fieldPath="validity_date"
                            fieldLabel="Gültigkeit bis"
                            type="date"
                            {...getFieldProps('validity_date', order.validity_date)}
                        />
                    )}
                </div>
            </section>

            {/* Besteller/Lieferant */}
            <section className="space-y-3 pb-4 border-b border-border/50">
                <h3 className="text-sm font-medium text-muted-foreground">Parteien</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {order.orderer && (
                        <div className="space-y-2">
                            <h4 className="text-xs font-medium text-muted-foreground">Besteller</h4>
                            {order.orderer.company && (
                                <EditableField
                                    fieldPath="orderer.company"
                                    fieldLabel="Firma"
                                    type="text"
                                    {...getFieldProps('orderer.company', order.orderer.company)}
                                />
                            )}
                            {order.orderer.name && (
                                <EditableField
                                    fieldPath="orderer.name"
                                    fieldLabel="Name"
                                    type="text"
                                    {...getFieldProps('orderer.name', order.orderer.name)}
                                />
                            )}
                            {(order.orderer.street || order.orderer.zip_code || order.orderer.city) && (
                                <div className="text-xs text-muted-foreground">
                                    {order.orderer.street}{order.orderer.street_number && ` ${order.orderer.street_number}`}<br />
                                    {order.orderer.zip_code} {order.orderer.city}
                                </div>
                            )}
                            {order.orderer_contact && (
                                <EditableField
                                    fieldPath="orderer_contact"
                                    fieldLabel="Kontakt"
                                    type="text"
                                    {...getFieldProps('orderer_contact', order.orderer_contact)}
                                />
                            )}
                        </div>
                    )}
                    {order.supplier && (
                        <div className="space-y-2">
                            <h4 className="text-xs font-medium text-muted-foreground">Lieferant</h4>
                            {order.supplier.company && (
                                <EditableField
                                    fieldPath="supplier.company"
                                    fieldLabel="Firma"
                                    type="text"
                                    {...getFieldProps('supplier.company', order.supplier.company)}
                                />
                            )}
                            {order.supplier.name && (
                                <EditableField
                                    fieldPath="supplier.name"
                                    fieldLabel="Name"
                                    type="text"
                                    {...getFieldProps('supplier.name', order.supplier.name)}
                                />
                            )}
                            {(order.supplier.street || order.supplier.zip_code || order.supplier.city) && (
                                <div className="text-xs text-muted-foreground">
                                    {order.supplier.street}{order.supplier.street_number && ` ${order.supplier.street_number}`}<br />
                                    {order.supplier.zip_code} {order.supplier.city}
                                </div>
                            )}
                            {order.supplier_contact && (
                                <EditableField
                                    fieldPath="supplier_contact"
                                    fieldLabel="Kontakt"
                                    type="text"
                                    {...getFieldProps('supplier_contact', order.supplier_contact)}
                                />
                            )}
                        </div>
                    )}
                </div>
            </section>

            {/* Lieferadresse (falls vorhanden) */}
            {order.delivery_address && (
                <section className="space-y-3 pb-4 border-b border-border/50">
                    <h3 className="text-sm font-medium text-muted-foreground">Lieferadresse</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {order.delivery_address.company && (
                            <EditableField
                                fieldPath="delivery_address.company"
                                fieldLabel="Firma"
                                type="text"
                                {...getFieldProps('delivery_address.company', order.delivery_address.company)}
                            />
                        )}
                        {order.delivery_address.street && (
                            <EditableField
                                fieldPath="delivery_address.street"
                                fieldLabel="Straße"
                                type="text"
                                {...getFieldProps('delivery_address.street', order.delivery_address.street)}
                            />
                        )}
                        <EditableField
                            fieldPath="delivery_address.zip_code"
                            fieldLabel="PLZ"
                            type="text"
                            {...getFieldProps('delivery_address.zip_code', order.delivery_address.zip_code)}
                        />
                        <EditableField
                            fieldPath="delivery_address.city"
                            fieldLabel="Ort"
                            type="text"
                            {...getFieldProps('delivery_address.city', order.delivery_address.city)}
                        />
                    </div>
                </section>
            )}

            {/* Beträge */}
            {(order.total_amount || order.currency) && (
                <section className="space-y-3 pb-4 border-b border-border/50">
                    <h3 className="text-sm font-medium text-muted-foreground">Beträge</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {order.total_amount !== undefined && (
                            <EditableField
                                fieldPath="total_amount"
                                fieldLabel="Gesamtbetrag"
                                type="currency"
                                {...getFieldProps('total_amount', order.total_amount)}
                            />
                        )}
                        {order.currency && (
                            <EditableField
                                fieldPath="currency"
                                fieldLabel="Währung"
                                type="text"
                                {...getFieldProps('currency', order.currency)}
                            />
                        )}
                    </div>
                </section>
            )}

            {/* Bedingungen */}
            {(order.payment_terms || order.delivery_terms || order.incoterms) && (
                <section className="space-y-3">
                    <h3 className="text-sm font-medium text-muted-foreground">Bedingungen</h3>
                    <div className="grid grid-cols-1 gap-3">
                        {order.payment_terms && (
                            <EditableField
                                fieldPath="payment_terms"
                                fieldLabel="Zahlungsbedingungen"
                                type="text"
                                {...getFieldProps('payment_terms', order.payment_terms)}
                            />
                        )}
                        {order.delivery_terms && (
                            <EditableField
                                fieldPath="delivery_terms"
                                fieldLabel="Lieferbedingungen"
                                type="text"
                                {...getFieldProps('delivery_terms', order.delivery_terms)}
                            />
                        )}
                        {order.incoterms && (
                            <EditableField
                                fieldPath="incoterms"
                                fieldLabel="Incoterms"
                                type="text"
                                {...getFieldProps('incoterms', order.incoterms)}
                            />
                        )}
                    </div>
                </section>
            )}

            {/* Positionen (falls vorhanden) */}
            {order.line_items && order.line_items.length > 0 && (
                <section className="space-y-3 pt-4 border-t border-border/50">
                    <h3 className="text-sm font-medium text-muted-foreground">
                        Positionen ({order.line_items.length})
                    </h3>
                    <div className="space-y-2">
                        {order.line_items.map((item, index) => (
                            <div
                                key={index}
                                className="p-3 bg-muted/30 rounded-md text-sm space-y-1"
                            >
                                <div className="flex justify-between">
                                    <span className="font-medium">
                                        {item.position}. {item.description || 'Keine Beschreibung'}
                                    </span>
                                    {item.total_price !== undefined && (
                                        <span className="font-mono">
                                            {item.total_price.toLocaleString('de-DE', {
                                                minimumFractionDigits: 2,
                                                maximumFractionDigits: 2,
                                            })} {order.currency || '€'}
                                        </span>
                                    )}
                                </div>
                                <div className="flex gap-4 text-xs text-muted-foreground">
                                    {item.article_number && <span>Art.-Nr.: {item.article_number}</span>}
                                    {item.quantity !== undefined && item.unit && (
                                        <span>Menge: {item.quantity} {item.unit}</span>
                                    )}
                                    {item.unit_price !== undefined && (
                                        <span>Stückpreis: {item.unit_price.toLocaleString('de-DE', {
                                            minimumFractionDigits: 2,
                                            maximumFractionDigits: 2,
                                        })}</span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </section>
            )}
        </>
    )
}

interface ContractSectionsProps {
    contract: NonNullable<UseExtractedDataForReviewReturn['contractData']>
    corrections: UseFieldCorrectionsReturn
    extractedDataReview: UseExtractedDataForReviewReturn
    disabled: boolean
}

function ContractSections({ contract, corrections, extractedDataReview, disabled }: ContractSectionsProps) {
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
    const getFieldProps = (field: string, value: string | number | boolean | null | undefined) => {
        const correction = getCorrection(field)
        const validationError = getValidationError(field)
        const normalizedValue = value ?? null

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
        <>
            {/* Vertragsidentifikation */}
            <section className="space-y-3 pb-4 border-b border-border/50">
                <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    Vertragsidentifikation
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <EditableField
                        fieldPath="contract_number"
                        fieldLabel="Vertragsnummer"
                        type="text"
                        {...getFieldProps('contract_number', contract.contract_number)}
                    />
                    {contract.contract_type && (
                        <EditableField
                            fieldPath="contract_type"
                            fieldLabel="Vertragsart"
                            type="text"
                            {...getFieldProps('contract_type', contract.contract_type)}
                        />
                    )}
                    {contract.previous_contract && (
                        <EditableField
                            fieldPath="previous_contract"
                            fieldLabel="Vorvertrag"
                            type="text"
                            {...getFieldProps('previous_contract', contract.previous_contract)}
                        />
                    )}
                </div>
            </section>

            {/* Laufzeit */}
            <section className="space-y-3 pb-4 border-b border-border/50">
                <h3 className="text-sm font-medium text-muted-foreground">Laufzeit</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {contract.contract_date && (
                        <EditableField
                            fieldPath="contract_date"
                            fieldLabel="Vertragsdatum"
                            type="date"
                            {...getFieldProps('contract_date', contract.contract_date)}
                        />
                    )}
                    <EditableField
                        fieldPath="start_date"
                        fieldLabel="Beginn"
                        type="date"
                        {...getFieldProps('start_date', contract.start_date)}
                    />
                    <EditableField
                        fieldPath="end_date"
                        fieldLabel="Ende"
                        type="date"
                        {...getFieldProps('end_date', contract.end_date)}
                    />
                    {contract.duration_months !== undefined && (
                        <EditableField
                            fieldPath="duration_months"
                            fieldLabel="Laufzeit (Monate)"
                            type="number"
                            {...getFieldProps('duration_months', contract.duration_months)}
                        />
                    )}
                </div>

                {/* Kündigungsinformationen */}
                {(contract.notice_period || contract.notice_deadline || contract.auto_renewal !== undefined) && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 pt-3 border-t border-border/30">
                        {contract.notice_period && (
                            <EditableField
                                fieldPath="notice_period"
                                fieldLabel="Kündigungsfrist"
                                type="text"
                                {...getFieldProps('notice_period', contract.notice_period)}
                            />
                        )}
                        {contract.notice_deadline && (
                            <EditableField
                                fieldPath="notice_deadline"
                                fieldLabel="Kündigungstermin"
                                type="date"
                                {...getFieldProps('notice_deadline', contract.notice_deadline)}
                            />
                        )}
                        {contract.auto_renewal !== undefined && (
                            <div className="flex items-center gap-2 text-sm">
                                <span className="text-muted-foreground">Automatische Verlängerung:</span>
                                <span className={contract.auto_renewal ? 'text-green-600 font-medium' : 'text-muted-foreground'}>
                                    {contract.auto_renewal ? 'Ja' : 'Nein'}
                                </span>
                            </div>
                        )}
                        {contract.renewal_period && (
                            <EditableField
                                fieldPath="renewal_period"
                                fieldLabel="Verlängerungszeitraum"
                                type="text"
                                {...getFieldProps('renewal_period', contract.renewal_period)}
                            />
                        )}
                    </div>
                )}
            </section>

            {/* Vertragsparteien */}
            <section className="space-y-3 pb-4 border-b border-border/50">
                <h3 className="text-sm font-medium text-muted-foreground">Vertragsparteien</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {contract.party_a && (
                        <div className="space-y-2">
                            <h4 className="text-xs font-medium text-muted-foreground">Partei A</h4>
                            {contract.party_a.company && (
                                <EditableField
                                    fieldPath="party_a.company"
                                    fieldLabel="Firma"
                                    type="text"
                                    {...getFieldProps('party_a.company', contract.party_a.company)}
                                />
                            )}
                            {contract.party_a.name && (
                                <EditableField
                                    fieldPath="party_a.name"
                                    fieldLabel="Name"
                                    type="text"
                                    {...getFieldProps('party_a.name', contract.party_a.name)}
                                />
                            )}
                            {(contract.party_a.street || contract.party_a.zip_code || contract.party_a.city) && (
                                <div className="text-xs text-muted-foreground">
                                    {contract.party_a.street}{contract.party_a.street_number && ` ${contract.party_a.street_number}`}<br />
                                    {contract.party_a.zip_code} {contract.party_a.city}
                                </div>
                            )}
                            {contract.party_a_signatory && (
                                <EditableField
                                    fieldPath="party_a_signatory"
                                    fieldLabel="Unterzeichner"
                                    type="text"
                                    {...getFieldProps('party_a_signatory', contract.party_a_signatory)}
                                />
                            )}
                        </div>
                    )}
                    {contract.party_b && (
                        <div className="space-y-2">
                            <h4 className="text-xs font-medium text-muted-foreground">Partei B</h4>
                            {contract.party_b.company && (
                                <EditableField
                                    fieldPath="party_b.company"
                                    fieldLabel="Firma"
                                    type="text"
                                    {...getFieldProps('party_b.company', contract.party_b.company)}
                                />
                            )}
                            {contract.party_b.name && (
                                <EditableField
                                    fieldPath="party_b.name"
                                    fieldLabel="Name"
                                    type="text"
                                    {...getFieldProps('party_b.name', contract.party_b.name)}
                                />
                            )}
                            {(contract.party_b.street || contract.party_b.zip_code || contract.party_b.city) && (
                                <div className="text-xs text-muted-foreground">
                                    {contract.party_b.street}{contract.party_b.street_number && ` ${contract.party_b.street_number}`}<br />
                                    {contract.party_b.zip_code} {contract.party_b.city}
                                </div>
                            )}
                            {contract.party_b_signatory && (
                                <EditableField
                                    fieldPath="party_b_signatory"
                                    fieldLabel="Unterzeichner"
                                    type="text"
                                    {...getFieldProps('party_b_signatory', contract.party_b_signatory)}
                                />
                            )}
                        </div>
                    )}
                </div>
            </section>

            {/* Vertragswerte */}
            {(contract.contract_value !== undefined || contract.monthly_value !== undefined || contract.currency) && (
                <section className="space-y-3 pb-4 border-b border-border/50">
                    <h3 className="text-sm font-medium text-muted-foreground">Vertragswerte</h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        {contract.contract_value !== undefined && (
                            <EditableField
                                fieldPath="contract_value"
                                fieldLabel="Vertragswert"
                                type="currency"
                                {...getFieldProps('contract_value', contract.contract_value)}
                            />
                        )}
                        {contract.monthly_value !== undefined && (
                            <EditableField
                                fieldPath="monthly_value"
                                fieldLabel="Monatlicher Wert"
                                type="currency"
                                {...getFieldProps('monthly_value', contract.monthly_value)}
                            />
                        )}
                        {contract.currency && (
                            <EditableField
                                fieldPath="currency"
                                fieldLabel="Währung"
                                type="text"
                                {...getFieldProps('currency', contract.currency)}
                            />
                        )}
                    </div>
                </section>
            )}

            {/* Vertragsgegenstand */}
            {contract.subject && (
                <section className="space-y-3">
                    <h3 className="text-sm font-medium text-muted-foreground">Vertragsgegenstand</h3>
                    <EditableField
                        fieldPath="subject"
                        fieldLabel="Gegenstand"
                        type="text"
                        {...getFieldProps('subject', contract.subject)}
                    />
                </section>
            )}
        </>
    )
}
