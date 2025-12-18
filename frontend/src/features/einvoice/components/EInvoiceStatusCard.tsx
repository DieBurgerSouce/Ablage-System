/**
 * EInvoiceStatusCard - Zeigt E-Invoice Status für ein Dokument.
 *
 * Features:
 * - Zeigt ob Dokument E-Invoice hat (ZUGFeRD/XRechnung)
 * - Format, Profil, Validierungsstatus
 * - Quick-Actions: Download, Validieren, Generieren
 */

import {
    FileText,
    CheckCircle2,
    AlertTriangle,
    XCircle,
    Download,
    RefreshCw,
    FileCode,
    Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { useEInvoiceStatus, useDownloadXml, useValidateByDocumentId } from "../hooks/useEInvoice";
import { FORMAT_LABELS, PROFILE_LABELS } from "../types/einvoice.types";
import type { ZUGFeRDProfile } from "../types/einvoice.types";

interface EInvoiceStatusCardProps {
    documentId: string;
    onGenerateClick?: () => void;
    className?: string;
}

export function EInvoiceStatusCard({
    documentId,
    onGenerateClick,
    className,
}: EInvoiceStatusCardProps) {
    const { data: status, isLoading, error } = useEInvoiceStatus(documentId);
    const downloadXml = useDownloadXml();
    const validateMutation = useValidateByDocumentId();

    // Loading State
    if (isLoading) {
        return (
            <Card className={className}>
                <CardHeader className="pb-2">
                    <div className="flex items-center gap-2">
                        <Skeleton className="h-5 w-5" />
                        <Skeleton className="h-5 w-32" />
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="space-y-2">
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-3/4" />
                    </div>
                </CardContent>
            </Card>
        );
    }

    // Error State
    if (error) {
        return (
            <Card className={className}>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2 text-muted-foreground">
                        <AlertTriangle className="h-4 w-4" />
                        E-Rechnung
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-sm text-muted-foreground">
                        Status konnte nicht geladen werden
                    </p>
                </CardContent>
            </Card>
        );
    }

    // No E-Invoice
    if (!status?.hasEinvoice) {
        return (
            <Card className={className}>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        E-Rechnung
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-sm text-muted-foreground mb-3">
                        Keine E-Rechnung vorhanden
                    </p>
                    {onGenerateClick && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onGenerateClick}
                            className="w-full"
                        >
                            <FileCode className="h-4 w-4 mr-2" />
                            E-Rechnung erstellen
                        </Button>
                    )}
                </CardContent>
            </Card>
        );
    }

    // Has E-Invoice
    const formatLabel = status.format ? FORMAT_LABELS[status.format] || status.format : 'Unbekannt';
    const profileLabel = status.profile ?
        PROFILE_LABELS[status.profile as ZUGFeRDProfile] || status.profile :
        undefined;

    return (
        <Card className={className}>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <FileText className="h-4 w-4 text-primary" />
                        E-Rechnung
                    </CardTitle>
                    <ValidationBadge isValid={status.isValid} />
                </div>
            </CardHeader>
            <CardContent className="space-y-3">
                {/* Format & Profile */}
                <div className="space-y-1">
                    <div className="flex items-center gap-2 text-sm">
                        <span className="text-muted-foreground">Format:</span>
                        <Badge variant="outline">{formatLabel}</Badge>
                    </div>
                    {profileLabel && (
                        <div className="flex items-center gap-2 text-sm">
                            <span className="text-muted-foreground">Profil:</span>
                            <span>{profileLabel}</span>
                        </div>
                    )}
                    {status.version && (
                        <div className="flex items-center gap-2 text-sm">
                            <span className="text-muted-foreground">Version:</span>
                            <span>{status.version}</span>
                        </div>
                    )}
                </div>

                {/* Leitweg-ID (XRechnung) */}
                {status.leitwegId && (
                    <div className="text-sm">
                        <span className="text-muted-foreground">Leitweg-ID:</span>
                        <code className="ml-2 px-1 py-0.5 bg-muted rounded text-xs">
                            {status.leitwegId}
                        </code>
                    </div>
                )}

                {/* Validation Summary */}
                {status.validationSummary && (
                    <div className="text-sm flex items-center gap-2">
                        {status.validationSummary.errorCount > 0 ? (
                            <Badge variant="destructive">
                                {status.validationSummary.errorCount} Fehler
                            </Badge>
                        ) : null}
                        {status.validationSummary.warningCount > 0 ? (
                            <Badge variant="secondary">
                                {status.validationSummary.warningCount} Warnungen
                            </Badge>
                        ) : null}
                    </div>
                )}

                {/* Origin */}
                <div className="text-xs text-muted-foreground">
                    {status.wasGenerated && "Generiert"}
                    {status.wasExtracted && "Aus PDF extrahiert"}
                    {status.createdAt && (
                        <span className="ml-1">
                            am {new Date(status.createdAt).toLocaleDateString('de-DE')}
                        </span>
                    )}
                </div>

                {/* Actions */}
                <div className="flex gap-2 pt-2">
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => downloadXml.mutate(documentId)}
                                    disabled={downloadXml.isPending}
                                >
                                    {downloadXml.isPending ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <Download className="h-4 w-4" />
                                    )}
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>XML herunterladen</TooltipContent>
                        </Tooltip>

                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => validateMutation.mutate({ documentId })}
                                    disabled={validateMutation.isPending}
                                >
                                    {validateMutation.isPending ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <RefreshCw className="h-4 w-4" />
                                    )}
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>Erneut validieren</TooltipContent>
                        </Tooltip>
                    </TooltipProvider>

                    {onGenerateClick && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onGenerateClick}
                            className="flex-1"
                        >
                            <FileCode className="h-4 w-4 mr-2" />
                            Neu generieren
                        </Button>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

// Validation Badge Helper
function ValidationBadge({ isValid }: { isValid?: boolean }) {
    if (isValid === undefined) {
        return (
            <Badge variant="secondary" className="text-xs">
                Nicht validiert
            </Badge>
        );
    }

    if (isValid) {
        return (
            <Badge variant="default" className="text-xs bg-green-600">
                <CheckCircle2 className="h-3 w-3 mr-1" />
                Gültig
            </Badge>
        );
    }

    return (
        <Badge variant="destructive" className="text-xs">
            <XCircle className="h-3 w-3 mr-1" />
            Ungültig
        </Badge>
    );
}
