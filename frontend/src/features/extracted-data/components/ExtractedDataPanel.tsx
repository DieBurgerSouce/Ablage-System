/**
 * ExtractedDataPanel - Haupt-Container fuer strukturierte Dokumentendaten.
 *
 * Zeigt je nach Dokumenttyp die entsprechende Anzeige-Komponente:
 * - InvoiceDataDisplay fuer Rechnungen
 * - OrderDataDisplay fuer Bestellungen (TODO)
 * - ContractDataDisplay fuer Vertraege (TODO)
 */

import { FileText, AlertTriangle, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfidenceIndicator } from "@/features/validation/components/ConfidenceIndicator";
import { useExtractedData } from "../hooks/useExtractedData";
import { InvoiceDataDisplay } from "./InvoiceDataDisplay";
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
            return (
                <Card className={className}>
                    <CardContent className="py-8">
                        <div className="text-center text-muted-foreground">
                            <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                            <p className="text-lg font-medium mb-1">
                                Keine strukturierten Daten verfuegbar
                            </p>
                            <p className="text-sm">
                                Dieses Dokument wurde noch nicht strukturiert verarbeitet.
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
                        <p>Keine strukturierten Daten verfuegbar</p>
                    </div>
                </CardContent>
            </Card>
        );
    }

    const documentType = data.classification?.document_type || "unknown";
    const confidence = data.classification?.confidence || 0;
    const needsReview = data.needs_review || false;
    const warnings = data.extraction_warnings || [];

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
                            {DOCUMENT_TYPE_LABELS[documentType]}
                        </Badge>
                    </div>
                </div>

                {/* Review-Warnung */}
                {needsReview && (
                    <Alert variant="default" className="mt-4 border-orange-200 bg-orange-50 dark:border-orange-800 dark:bg-orange-950/30">
                        <AlertTriangle className="h-4 w-4 text-orange-600" />
                        <AlertTitle className="text-orange-800 dark:text-orange-400">
                            Manuelle Pruefung erforderlich
                        </AlertTitle>
                        <AlertDescription className="text-orange-700 dark:text-orange-300">
                            {warnings.length > 0 ? (
                                <ul className="list-disc list-inside mt-1">
                                    {warnings.map((warning, idx) => (
                                        <li key={idx}>{warning}</li>
                                    ))}
                                </ul>
                            ) : (
                                "Die extrahierten Daten sollten manuell ueberprueft werden."
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
                    <div className="text-center text-muted-foreground py-8">
                        <p>Bestellungsanzeige wird in einer zukuenftigen Version implementiert.</p>
                        <pre className="mt-4 text-xs text-left bg-muted p-4 rounded overflow-auto max-h-96">
                            {JSON.stringify(data.order, null, 2)}
                        </pre>
                    </div>
                )}

                {documentType === "contract" && data.contract && (
                    <div className="text-center text-muted-foreground py-8">
                        <p>Vertragsanzeige wird in einer zukuenftigen Version implementiert.</p>
                        <pre className="mt-4 text-xs text-left bg-muted p-4 rounded overflow-auto max-h-96">
                            {JSON.stringify(data.contract, null, 2)}
                        </pre>
                    </div>
                )}

                {documentType === "unknown" && (
                    <div className="text-center text-muted-foreground py-8">
                        <p>Dokumenttyp konnte nicht erkannt werden.</p>
                    </div>
                )}

                {/* Allgemeine Entities (fallback fuer alle Typen) */}
                {((data.ibans?.length ?? 0) > 0 ||
                    (data.vat_ids?.length ?? 0) > 0 ||
                    (data.companies?.length ?? 0) > 0) && (
                    <div className="mt-6 pt-6 border-t">
                        <h4 className="text-sm font-medium mb-4">
                            Weitere erkannte Entitaeten
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
