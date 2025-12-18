/**
 * DATEV Export Warnungen Komponente
 *
 * Zeigt Warnungen und uebersprungene Dokumente an.
 */

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Button } from '@/components/ui/button';
import { AlertTriangle, ChevronDown, FileX } from 'lucide-react';

interface ExportWarningsProps {
    warnings: string[];
    skippedCount: number;
    skippedReasons: Record<string, number>;
}

export function ExportWarnings({ warnings, skippedCount, skippedReasons }: ExportWarningsProps) {
    if (warnings.length === 0 && skippedCount === 0) {
        return null;
    }

    return (
        <div className="space-y-4">
            {/* Warnungen */}
            {warnings.length > 0 && (
                <Alert variant="default" className="border-yellow-200 bg-yellow-50">
                    <AlertTriangle className="h-4 w-4 text-yellow-600" />
                    <AlertTitle className="text-yellow-800">Hinweise</AlertTitle>
                    <AlertDescription className="text-yellow-700">
                        <ul className="list-disc list-inside mt-2 space-y-1">
                            {warnings.map((warning, index) => (
                                <li key={index}>{warning}</li>
                            ))}
                        </ul>
                    </AlertDescription>
                </Alert>
            )}

            {/* Uebersprungene Dokumente */}
            {skippedCount > 0 && (
                <Collapsible>
                    <Alert variant="default" className="border-orange-200 bg-orange-50">
                        <FileX className="h-4 w-4 text-orange-600" />
                        <AlertTitle className="text-orange-800 flex items-center justify-between">
                            <span>
                                {skippedCount} Dokument{skippedCount !== 1 ? 'e' : ''} uebersprungen
                            </span>
                            <CollapsibleTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-6 px-2 text-orange-700 hover:text-orange-800 hover:bg-orange-100"
                                >
                                    Details
                                    <ChevronDown className="ml-1 h-3 w-3" />
                                </Button>
                            </CollapsibleTrigger>
                        </AlertTitle>
                        <CollapsibleContent>
                            <AlertDescription className="text-orange-700 mt-2">
                                <ul className="space-y-1">
                                    {Object.entries(skippedReasons).map(([reason, count]) => (
                                        <li key={reason} className="flex justify-between">
                                            <span>{formatSkippedReason(reason)}</span>
                                            <span className="font-mono">{count}x</span>
                                        </li>
                                    ))}
                                </ul>
                            </AlertDescription>
                        </CollapsibleContent>
                    </Alert>
                </Collapsible>
            )}
        </div>
    );
}

/**
 * Formatiert den Grund fuer uebersprungene Dokumente
 */
function formatSkippedReason(reason: string): string {
    const reasonMap: Record<string, string> = {
        no_amount: 'Kein Betrag vorhanden',
        no_invoice_date: 'Kein Rechnungsdatum',
        no_invoice_number: 'Keine Rechnungsnummer',
        already_exported: 'Bereits exportiert',
        invalid_document_type: 'Ungueltiger Dokumenttyp',
        missing_vendor_info: 'Fehlende Lieferantendaten',
        invalid_tax_rate: 'Ungueltiger Steuersatz',
    };

    return reasonMap[reason] || reason;
}
