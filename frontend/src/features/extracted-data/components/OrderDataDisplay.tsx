/**
 * OrderDataDisplay - Zeigt alle extrahierten Bestellungsdaten.
 */

import { Truck, CreditCard, Hash, Calendar } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
    CopyableField,
    formatCurrency,
    formatDate,
} from "./CopyableField";
import { AddressCard } from "./AddressCard";
import { LineItemsTable } from "./LineItemsTable";
import type { ExtractedOrderData } from "../types/extracted-data.types";

interface OrderDataDisplayProps {
    order: ExtractedOrderData;
    className?: string;
}

export function OrderDataDisplay({ order, className }: OrderDataDisplayProps) {
    const currency = order.currency || "EUR";

    return (
        <div className={className}>
            {/* Identifikation */}
            <Card className="mb-4">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Hash className="h-4 w-4" />
                        Bestellidentifikation
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <dl className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <CopyableField
                            label="Bestellnummer"
                            value={order.order_number}
                        />
                        <div className="space-y-1">
                            <dt className="text-sm font-medium text-muted-foreground">
                                Bestelldatum
                            </dt>
                            <dd className="text-sm">
                                {formatDate(order.order_date)}
                            </dd>
                        </div>
                        {order.quotation_number && (
                            <CopyableField
                                label="Angebotsnummer"
                                value={order.quotation_number}
                            />
                        )}
                        {order.customer_order_number && (
                            <CopyableField
                                label="Kunden-Bestellnr."
                                value={order.customer_order_number}
                            />
                        )}
                    </dl>

                    {/* Zusätzliche Daten */}
                    {(order.confirmation_date || order.validity_date) && (
                        <>
                            <Separator className="my-4" />
                            <dl className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                {order.confirmation_date && (
                                    <div className="space-y-1">
                                        <dt className="text-sm font-medium text-muted-foreground">
                                            Bestätigungsdatum
                                        </dt>
                                        <dd className="text-sm">
                                            {formatDate(order.confirmation_date)}
                                        </dd>
                                    </div>
                                )}
                                {order.validity_date && (
                                    <div className="space-y-1">
                                        <dt className="text-sm font-medium text-muted-foreground">
                                            Gültig bis
                                        </dt>
                                        <dd className="text-sm">
                                            {formatDate(order.validity_date)}
                                        </dd>
                                    </div>
                                )}
                            </dl>
                        </>
                    )}
                </CardContent>
            </Card>

            {/* Adressen: Besteller und Lieferant */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <AddressCard
                    title="Besteller"
                    address={order.orderer}
                    contact={order.orderer_contact}
                />
                <AddressCard
                    title="Lieferant"
                    address={order.supplier}
                    contact={order.supplier_contact}
                />
            </div>

            {/* Lieferinformationen */}
            {(order.delivery_address || order.delivery_date || order.delivery_terms || order.incoterms) && (
                <Card className="mb-4">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <Truck className="h-4 w-4" />
                            Lieferung
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {order.delivery_address && (
                                <div className="space-y-2">
                                    <div className="text-sm font-medium text-muted-foreground">
                                        Lieferadresse
                                    </div>
                                    <div className="text-sm">
                                        {order.delivery_address.company && (
                                            <div className="font-medium">{order.delivery_address.company}</div>
                                        )}
                                        {order.delivery_address.name && (
                                            <div>{order.delivery_address.name}</div>
                                        )}
                                        {order.delivery_address.street && (
                                            <div>{order.delivery_address.street}</div>
                                        )}
                                        {(order.delivery_address.zip || order.delivery_address.city) && (
                                            <div>
                                                {order.delivery_address.zip} {order.delivery_address.city}
                                            </div>
                                        )}
                                        {order.delivery_address.country && (
                                            <div>{order.delivery_address.country}</div>
                                        )}
                                    </div>
                                </div>
                            )}

                            <div className="space-y-3">
                                {order.delivery_date && (
                                    <div className="flex items-center gap-2">
                                        <Calendar className="h-4 w-4 text-muted-foreground" />
                                        <span className="text-sm text-muted-foreground">Liefertermin:</span>
                                        <span className="text-sm font-medium">
                                            {formatDate(order.delivery_date)}
                                        </span>
                                    </div>
                                )}
                                {order.delivery_terms && (
                                    <div className="space-y-1">
                                        <dt className="text-sm font-medium text-muted-foreground">
                                            Lieferbedingungen
                                        </dt>
                                        <dd className="text-sm">{order.delivery_terms}</dd>
                                    </div>
                                )}
                                {order.incoterms && (
                                    <div className="space-y-1">
                                        <dt className="text-sm font-medium text-muted-foreground">
                                            Incoterms
                                        </dt>
                                        <dd className="text-sm font-mono">{order.incoterms}</dd>
                                    </div>
                                )}
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Positionen */}
            {order.line_items && order.line_items.length > 0 && (
                <LineItemsTable
                    items={order.line_items}
                    currency={currency}
                    className="mb-4"
                    title="Bestellpositionen"
                />
            )}

            {/* Bestellsumme */}
            <Card className="mb-4">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <CreditCard className="h-4 w-4" />
                        Bestellsumme
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Gesamtbetrag</span>
                        <span className="text-2xl font-bold text-primary">
                            {formatCurrency(order.total_amount, currency)}
                        </span>
                    </div>
                    {order.payment_terms && (
                        <p className="text-sm text-muted-foreground mt-2">
                            Zahlungsbedingungen: {order.payment_terms}
                        </p>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
