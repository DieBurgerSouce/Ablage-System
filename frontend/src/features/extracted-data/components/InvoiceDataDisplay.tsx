/**
 * InvoiceDataDisplay - Zeigt alle extrahierten Rechnungsdaten.
 */

import { Calendar, Hash, CreditCard, Building, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import {
    CopyableField,
    formatCurrency,
    formatDate,
    formatIBAN,
} from "./CopyableField";
import { AddressCard } from "./AddressCard";
import { PaymentTermsCard } from "./PaymentTermsCard";
import { LineItemsTable } from "./LineItemsTable";
import type { ExtractedInvoiceData } from "../types/extracted-data.types";

interface InvoiceDataDisplayProps {
    invoice: ExtractedInvoiceData;
    className?: string;
}

export function InvoiceDataDisplay({ invoice, className }: InvoiceDataDisplayProps) {
    const currency = invoice.currency || "EUR";

    return (
        <div className={className}>
            {/* Identifikation */}
            <Card className="mb-4">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Hash className="h-4 w-4" />
                        Identifikation
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <dl className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <CopyableField
                            label="Rechnungsnummer"
                            value={invoice.invoice_number}
                        />
                        <div className="space-y-1">
                            <dt className="text-sm font-medium text-muted-foreground">
                                Rechnungsdatum
                            </dt>
                            <dd className="text-sm">
                                {formatDate(invoice.invoice_date)}
                            </dd>
                        </div>
                        <div className="space-y-1">
                            <dt className="text-sm font-medium text-muted-foreground">
                                Fälligkeitsdatum
                            </dt>
                            <dd className="text-sm">{formatDate(invoice.due_date)}</dd>
                        </div>
                        <div className="space-y-1">
                            <dt className="text-sm font-medium text-muted-foreground">
                                Skontodatum
                            </dt>
                            <dd className="text-sm">
                                {invoice.discount_due_date ? formatDate(invoice.discount_due_date) : "-"}
                            </dd>
                        </div>
                    </dl>

                    {/* Zusätzliche Referenzen */}
                    {(invoice.order_number || invoice.delivery_note_number || invoice.customer_number || invoice.supplier_number) && (
                        <>
                            <Separator className="my-4" />
                            <dl className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                {invoice.order_number && (
                                    <CopyableField
                                        label="Bestellnummer"
                                        value={invoice.order_number}
                                    />
                                )}
                                {invoice.delivery_note_number && (
                                    <CopyableField
                                        label="Lieferscheinnummer"
                                        value={invoice.delivery_note_number}
                                    />
                                )}
                                {invoice.customer_number && (
                                    <CopyableField
                                        label="Kundennummer"
                                        value={invoice.customer_number}
                                    />
                                )}
                                {invoice.supplier_number && (
                                    <CopyableField
                                        label="Lieferantennummer"
                                        value={invoice.supplier_number}
                                    />
                                )}
                            </dl>
                        </>
                    )}

                    {/* Leistungszeitraum */}
                    {(invoice.service_period_start || invoice.service_period_end) && (
                        <>
                            <Separator className="my-4" />
                            <div className="flex items-center gap-2">
                                <Calendar className="h-4 w-4 text-muted-foreground" />
                                <span className="text-sm text-muted-foreground">
                                    Leistungszeitraum:{" "}
                                </span>
                                <span className="text-sm">
                                    {formatDate(invoice.service_period_start)} -{" "}
                                    {formatDate(invoice.service_period_end)}
                                </span>
                            </div>
                        </>
                    )}
                </CardContent>
            </Card>

            {/* Adressen */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <AddressCard title="Absender" address={invoice.sender} />
                <AddressCard title="Empfänger" address={invoice.recipient} />
            </div>

            {/* Beträge */}
            <Card className="mb-4">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <CreditCard className="h-4 w-4" />
                        Beträge
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="space-y-1">
                            <dt className="text-sm font-medium text-muted-foreground">
                                Nettobetrag
                            </dt>
                            <dd className="text-lg font-medium">
                                {formatCurrency(invoice.net_amount, currency)}
                            </dd>
                        </div>
                        <div className="space-y-1">
                            <dt className="text-sm font-medium text-muted-foreground">
                                MwSt {invoice.vat_rate != null && `(${invoice.vat_rate}%)`}
                            </dt>
                            <dd className="text-lg font-medium">
                                {formatCurrency(invoice.vat_amount, currency)}
                            </dd>
                        </div>
                        <div className="space-y-1 col-span-2">
                            <dt className="text-sm font-medium text-muted-foreground">
                                Bruttobetrag
                            </dt>
                            <dd className="text-2xl font-bold text-primary">
                                {formatCurrency(invoice.gross_amount, currency)}
                            </dd>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Zahlungsbedingungen */}
            {(invoice.payment_terms ||
                invoice.payment_terms_days ||
                invoice.discount_percent ||
                invoice.due_date) && (
                <PaymentTermsCard
                    paymentTerms={invoice.payment_terms}
                    paymentTermsDays={invoice.payment_terms_days}
                    discountPercent={invoice.discount_percent}
                    discountDays={invoice.discount_days}
                    discountAmount={invoice.discount_amount}
                    discountDueDate={invoice.discount_due_date}
                    dueDate={invoice.due_date}
                    earlyPaymentInfo={invoice.early_payment_info}
                    latePaymentInfo={invoice.late_payment_info}
                    currency={currency}
                    className="mb-4"
                />
            )}

            {/* Bankverbindung */}
            {invoice.sender_bank?.iban && (
                <Card className="mb-4">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <Building className="h-4 w-4" />
                            Bankverbindung
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <dl className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <CopyableField
                                label="IBAN"
                                value={invoice.sender_bank.iban}
                                format={formatIBAN}
                            />
                            {invoice.sender_bank.bic && (
                                <CopyableField
                                    label="BIC"
                                    value={invoice.sender_bank.bic}
                                />
                            )}
                            {invoice.sender_bank.bank_name && (
                                <div className="space-y-1">
                                    <dt className="text-sm font-medium text-muted-foreground">
                                        Bank
                                    </dt>
                                    <dd className="text-sm">{invoice.sender_bank.bank_name}</dd>
                                </div>
                            )}
                        </dl>
                    </CardContent>
                </Card>
            )}

            {/* USt-IDs */}
            {(invoice.sender_vat_id || invoice.recipient_vat_id) && (
                <Card className="mb-4">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium">
                            Steuerliche Angaben
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <dl className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {invoice.sender_vat_id && (
                                <CopyableField
                                    label="USt-IdNr. Absender"
                                    value={invoice.sender_vat_id}
                                />
                            )}
                            {invoice.sender_tax_number && (
                                <CopyableField
                                    label="Steuernummer Absender"
                                    value={invoice.sender_tax_number}
                                />
                            )}
                            {invoice.recipient_vat_id && (
                                <CopyableField
                                    label="USt-IdNr. Empfänger"
                                    value={invoice.recipient_vat_id}
                                />
                            )}
                        </dl>
                    </CardContent>
                </Card>
            )}

            {/* Reverse Charge / Steuerbefreiung */}
            {(invoice.is_reverse_charge || invoice.vat_exemption_reason || invoice.intra_community_supply) && (
                <Card className="mb-4">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4 text-amber-500" />
                            Steuerbefreiung
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        {invoice.is_reverse_charge && (
                            <div className="flex items-center gap-2">
                                <Badge variant="destructive">Reverse Charge</Badge>
                                <span className="text-sm text-muted-foreground">
                                    Steuerschuldnerschaft beim Leistungsempfänger
                                </span>
                            </div>
                        )}
                        {invoice.intra_community_supply && (
                            <div className="flex items-center gap-2">
                                <Badge variant="outline">Innergemeinschaftliche Lieferung</Badge>
                            </div>
                        )}
                        {invoice.vat_exemption_reason && (
                            <div className="text-sm">
                                <span className="font-medium">Grund: </span>
                                {invoice.vat_exemption_reason}
                            </div>
                        )}
                        {invoice.reverse_charge_note && (
                            <div className="text-xs text-muted-foreground italic border-l-2 border-amber-500 pl-2">
                                {invoice.reverse_charge_note}
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Positionen */}
            {invoice.line_items && invoice.line_items.length > 0 && (
                <LineItemsTable
                    items={invoice.line_items}
                    currency={currency}
                    className="mb-4"
                />
            )}

            {/* Kontaktdaten */}
            {(invoice.sender_email || invoice.sender_phone || invoice.sender_contact) && (
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium">Kontakt</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <dl className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {invoice.sender_email && (
                                <CopyableField
                                    label="E-Mail"
                                    value={invoice.sender_email}
                                />
                            )}
                            {invoice.sender_phone && (
                                <CopyableField
                                    label="Telefon"
                                    value={invoice.sender_phone}
                                />
                            )}
                            <div className="space-y-1">
                                <dt className="text-sm font-medium text-muted-foreground">
                                    Ansprechpartner
                                </dt>
                                <dd className="text-sm">
                                    {invoice.sender_contact || "-"}
                                </dd>
                            </div>
                        </dl>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
