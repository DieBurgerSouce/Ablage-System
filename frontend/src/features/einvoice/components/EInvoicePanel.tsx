/**
 * EInvoicePanel - E-Invoice Ansicht für den Document Viewer.
 *
 * Features:
 * - Zeigt E-Invoice Status
 * - Generator Dialog Integration
 * - Validierungs-Ergebnisse
 */

import { useState } from "react";
import { ExternalLink, Info } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { EInvoiceStatusCard } from "./EInvoiceStatusCard";
import { EInvoiceGeneratorDialog } from "./EInvoiceGeneratorDialog";
import { useEInvoiceStatus } from "../hooks/useEInvoice";

interface EInvoicePanelProps {
    documentId: string;
}

export function EInvoicePanel({ documentId }: EInvoicePanelProps) {
    const [generatorOpen, setGeneratorOpen] = useState(false);
    const { data: status, refetch } = useEInvoiceStatus(documentId);

    const handleGenerateSuccess = () => {
        refetch();
    };

    return (
        <div className="space-y-4">
            {/* E-Invoice Status Card */}
            <EInvoiceStatusCard
                documentId={documentId}
                onGenerateClick={() => setGeneratorOpen(true)}
            />

            {/* Info Alert wenn keine E-Rechnung vorhanden */}
            {status && !status.hasEinvoice && (
                <Alert>
                    <Info className="h-4 w-4" />
                    <AlertTitle>E-Rechnung erstellen</AlertTitle>
                    <AlertDescription className="space-y-2">
                        <p>
                            Dieses Dokument enthält noch keine E-Rechnung.
                            Sie können eine ZUGFeRD-PDF oder XRechnung-XML generieren.
                        </p>
                        <ul className="text-sm list-disc ml-4 space-y-1">
                            <li>
                                <strong>ZUGFeRD 2.x:</strong> PDF mit eingebettetem XML für B2B
                            </li>
                            <li>
                                <strong>XRechnung 3.0:</strong> XML für öffentliche Auftraggeber (B2G)
                            </li>
                        </ul>
                    </AlertDescription>
                </Alert>
            )}

            {/* Separator und Links */}
            <Separator />

            {/* Hilfreiche Links */}
            <div className="space-y-2">
                <h4 className="text-sm font-medium">Weitere Informationen</h4>
                <div className="flex flex-col gap-1">
                    <a
                        href="https://www.ferd-net.de/"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-muted-foreground hover:text-primary flex items-center gap-1"
                    >
                        <ExternalLink className="h-3 w-3" />
                        ZUGFeRD Standard
                    </a>
                    <a
                        href="https://www.xoev.de/xrechnung"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-muted-foreground hover:text-primary flex items-center gap-1"
                    >
                        <ExternalLink className="h-3 w-3" />
                        XRechnung (XOeV)
                    </a>
                    <a
                        href="https://www.e-rechnung-bund.de/"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-muted-foreground hover:text-primary flex items-center gap-1"
                    >
                        <ExternalLink className="h-3 w-3" />
                        E-Rechnungsportal Bund
                    </a>
                </div>
            </div>

            {/* Generator Dialog */}
            <EInvoiceGeneratorDialog
                documentId={documentId}
                open={generatorOpen}
                onOpenChange={setGeneratorOpen}
                onSuccess={handleGenerateSuccess}
            />
        </div>
    );
}
