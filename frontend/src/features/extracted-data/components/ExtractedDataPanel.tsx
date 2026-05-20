/**
 * ExtractedDataPanel - Haupt-Container für strukturierte Dokumentendaten.
 *
 * Zeigt je nach Dokumenttyp die entsprechende Anzeige-Komponente:
 * - InvoiceDataDisplay für Rechnungen
 * - OrderDataDisplay für Bestellungen
 * - ContractDataDisplay für Verträge
 */

import { FileText, AlertTriangle, Loader2, Clock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfidenceIndicator } from "@/features/validation/components/ConfidenceIndicator";
import { useExtractedData } from "../hooks/useExtractedData";
import { InvoiceDataDisplay } from "./InvoiceDataDisplay";
import { OrderDataDisplay } from "./OrderDataDisplay";
import { ContractDataDisplay } from "./ContractDataDisplay";
import { useQuery } from "@tanstack/react-query";
import { documentsService } from "@/lib/api/services/documents";
import type { ExtractedDocumentType } from "../types/extracted-data.types";

interface ExtractedDataPanelProps {
    documentId: string;
    className?: string;
}

// Dokumenttyp-Labels (Deutsch)
const DOCUMENT_TYPE_LABELS: Record<ExtractedDocumentType, string> = {
    invoice: "Rechnung",
    order: "Bestellung",
    contract: "Vertrag",
    delivery_note: "Lieferschein",
    receipt: "Quittung",
    unknown: "Unbekannt",
};

// Invoice-Direction Labels (spezifischer als "Rechnung")
const INVOICE_DIRECTION_LABELS: Record<string, string> = {
    incoming: "Eingangsrechnung",
    outgoing: "Ausgangsrechnung",
    unknown: "Rechnung",
};

// Badge-Varianten je nach Dokumenttyp
function getDocumentTypeBadgeVariant(
    type: ExtractedDocumentType
): "default" | "secondary" | "destructive" | "outline" {
    switch (type) {
        case "invoice":
            return "default";
        case "order":
            return "secondary";
        case "contract":
            return "outline";
        default:
            return "secondary";
    }
}

export function ExtractedDataPanel({
    documentId,
    className,
}: ExtractedDataPanelProps) {
    const { data, isLoading, error, isError } = useExtractedData(documentId);

    // Dokument-Status abfragen um zwischen "OCR läuft" und "Keine Daten" zu unterscheiden
    const { data: document } = useQuery({
        queryKey: ["document", documentId],
        queryFn: () => documentsService.getById(documentId),
        enabled: !!documentId && isError, // Nur laden wenn extracted-data Fehler
        staleTime: 10 * 1000, // 10 Sekunden - OCR-Status ändert sich
        refetchInterval: isError ? 5000 : false, // Polling nur wenn Fehler (OCR läuft evtl. noch)
    });

    // Loading State
    if (isLoading) {
        return (
            <Card className={className}>
                <CardHeader>
                    <div className="flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <CardTitle className="text-lg">Lade extrahierte Daten...</CardTitle>
                    </div>
                </CardHeader>
                <CardContent className="space-y-4">
                    <Skeleton className="h-24 w-full" />
                    <div className="grid grid-cols-2 gap-4">
                        <Skeleton className="h-32 w-full" />
                        <Skeleton className="h-32 w-full" />
                    </div>
                    <Skeleton className="h-48 w-full" />
                </CardContent>
            </Card>
        );
    }

    // Error State
    if (isError) {
        const errorMessage =
            (error as Error)?.message || "Unbekannter Fehler";
        const isNotFound = errorMessage.includes("404") || errorMessage.includes("nicht gefunden");

        if (isNotFound) {
            // Prüfen ob OCR noch läuft
            const ocrStatus = document?.ocrStatus;
            const isOcrProcessing = ocrStatus === 'processing' || ocrStatus === 'pending';

            if (isOcrProcessing) {
                // OCR läuft noch - zeige Ladeindikator mit Info
                return (
                    <Card className={className}>
                        <CardContent className="py-8">
                            <div className="text-center text-muted-foreground">
                                <div className="relative mx-auto mb-4 w-12 h-12">
                                    <Clock className="h-12 w-12 opacity-50" />
                                    <Loader2 className="h-6 w-6 animate-spin absolute bottom-0 right-0 text-primary" />
                                </div>
                                <p className="text-lg font-medium mb-1">
                                    OCR-Verarbeitung läuft...
                                </p>
                                <p className="text-sm">
                                    Die strukturierte Datenextraktion startet automatisch nach Abschluss der OCR-Verarbeitung.
                                </p>
                                <p className="text-xs mt-2 text-muted-foreground/70">
                                    Status: {ocrStatus === 'pending' ? 'Wartend' : 'Wird verarbeitet'}
                                </p>
                            </div>
                        </CardContent>
                    </Card>
                );
            }

            // OCR fertig aber keine strukturierten Daten vorhanden
            return (
                <Card className={className}>
                    <CardContent className="py-8">
                        <div className="text-center text-muted-foreground">
                            <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                            <p className="text-lg font-medium mb-1">
                                Keine strukturierten Daten verfügbar
                            </p>
                            <p className="text-sm">
                                {ocrStatus === 'completed'
                                    ? "Die strukturierte Datenextraktion wurde noch nicht durchgeführt."
                                    : ocrStatus === 'failed'
                                    ? "Die OCR-Verarbeitung ist fehlgeschlagen. Strukturierte Daten sind nicht verfügbar."
                                    : "Dieses Dokument wurde noch nicht strukturiert verarbeitet."}
                            </p>
                        </div>
                    </CardContent>
                </Card>
            );
        }

        return (
            <Alert variant="destructive" className={className}>
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Fehler beim Laden</AlertTitle>
                <AlertDescription>{errorMessage}</AlertDescription>
            </Alert>
        );
    }

    // No Data State
    if (!data) {
        return (
            <Card className={className}>
                <CardContent className="py-8">
                    <div className="text-center text-muted-foreground">
                        <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                        <p>Keine strukturierten Daten verfügbar</p>
                    </div>
                </CardContent>
            </Card>
        );
    }

    const documentType = data.classification?.document_type || "unknown";
    const confidence = data.classification?.confidence || 0;

    // needs_review und extraction_warnings sind auf den typspezifischen Daten,
    // nicht auf Top-Level (Backend Schema)
    const needsReview =
        data.invoice?.needs_review ||
        data.order?.needs_review ||
        data.contract?.needs_review ||
        false;
    const warnings =
        data.invoice?.extraction_warnings ||
        data.order?.extraction_warnings ||
        data.contract?.extraction_warnings ||
        [];

    // Bei Rechnungen: spezifisches Label basierend auf Direction
    const invoiceDirection = data.invoice?.invoice_direction || "unknown";
    const displayLabel = documentType === "invoice"
        ? INVOICE_DIRECTION_LABELS[invoiceDirection] || "Rechnung"
        : DOCUMENT_TYPE_LABELS[documentType];

    return (
        <Card className={className}>
            <CardHeader>
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-lg">
                        <FileText className="h-5 w-5" />
                        Extrahierte Daten
                    </CardTitle>
                    <div className="flex items-center gap-3">
                        <ConfidenceIndicator score={confidence} />
                        <Badge variant={getDocumentTypeBadgeVariant(documentType)}>
                            {displayLabel}
                        </Badge>
                    </div>
                </div>

                {/* Review-Warnung */}
                {needsReview && (
                    <Alert variant="default" className="mt-4 border-orange-200 bg-orange-50 dark:border-orange-800 dark:bg-orange-950/30">
                        <AlertTriangle className="h-4 w-4 text-orange-600" />
                        <AlertTitle className="text-orange-800 dark:text-orange-400">
                            Manuelle Prüfung erforderlich
                        </AlertTitle>
                        <AlertDescription className="text-orange-700 dark:text-orange-300">
                            {warnings.length > 0 ? (
                                <ul className="list-disc list-inside mt-1">
                                    {warnings.map((warning, idx) => (
                                        <li key={idx}>{warning}</li>
                                    ))}
                                </ul>
                            ) : (
                                "Die extrahierten Daten sollten manuell überprüft werden."
                            )}
                        </AlertDescription>
                    </Alert>
                )}
            </CardHeader>

            <CardContent>
                {/* Typ-spezifische Anzeige */}
                {documentType === "invoice" && data.invoice && (
                    <InvoiceDataDisplay invoice={data.invoice} />
                )}

                {documentType === "order" && data.order && (
                    <OrderDataDisplay order={data.order} />
                )}

                {documentType === "contract" && data.contract && (
                    <ContractDataDisplay contract={data.contract} />
                )}

                {documentType === "unknown" && (
                    <div className="text-center text-muted-foreground py-8">
                        <p>Dokumenttyp konnte nicht erkannt werden.</p>
                    </div>
                )}

                {/* Allgemeine Entities (fallback für alle Typen) */}
                {((data.ibans?.length ?? 0) > 0 ||
                    (data.vat_ids?.length ?? 0) > 0 ||
                    (data.companies?.length ?? 0) > 0) && (
                    <div className="mt-6 pt-6 border-t">
                        <h4 className="text-sm font-medium mb-4">
                            Weitere erkannte Entitäten
                        </h4>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                            {data.ibans && data.ibans.length > 0 && (
                                <div>
                                    <dt className="font-medium text-muted-foreground mb-1">
                                        IBANs
                                    </dt>
                                    <dd>
                                        {data.ibans.map((iban, idx) => (
                                            <div key={idx} className="font-mono text-xs">
                                                {iban}
                                            </div>
                                        ))}
                                    </dd>
                                </div>
                            )}
                            {data.vat_ids && data.vat_ids.length > 0 && (
                                <div>
                                    <dt className="font-medium text-muted-foreground mb-1">
                                        USt-IDs
                                    </dt>
                                    <dd>
                                        {data.vat_ids.map((vatId, idx) => (
                                            <div key={idx} className="font-mono text-xs">
                                                {vatId}
                                            </div>
                                        ))}
                                    </dd>
                                </div>
                            )}
                            {data.companies && data.companies.length > 0 && (
                                <div>
                                    <dt className="font-medium text-muted-foreground mb-1">
                                        Firmen
                                    </dt>
                                    <dd>
                                        {data.companies.map((company, idx) => (
                                            <div key={idx} className="text-xs">
                                                {company}
                                            </div>
                                        ))}
                                    </dd>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
