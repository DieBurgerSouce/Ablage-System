/**
 * DATEV Export-Validierungs-Zusammenfassung (W3-F4 Vertrauens-Loop)
 *
 * Zeigt vor dem Export, welche Belege exportierbar sind und welche
 * übersprungen werden ("✓ 98 OK · ✗ 2 Fehler") — mit aufklappbarer
 * Fehlerliste samt Grund je Dokument. Gibt dem Nutzer Gewissheit, dass
 * der Export sauber ist, statt blind zu exportieren.
 */

import { useState } from 'react';
import { CheckCircle2, XCircle, ChevronDown, ChevronRight } from 'lucide-react';
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { DATEVValidationItem } from '@/lib/api/services/datev';

interface ExportValidationSummaryProps {
    results: DATEVValidationItem[];
}

export function ExportValidationSummary({ results }: ExportValidationSummaryProps) {
    const [showErrors, setShowErrors] = useState(false);

    if (!results || results.length === 0) {
        return null;
    }

    const okCount = results.filter((r) => r.status === 'ok').length;
    const errors = results.filter((r) => r.status === 'error');
    const hasErrors = errors.length > 0;

    return (
        <Card
            className={hasErrors ? 'border-amber-200' : 'border-green-200'}
            data-testid="export-validation-summary"
        >
            <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-3 text-base">
                    <span className="flex items-center gap-1.5 text-green-700">
                        <CheckCircle2 className="h-5 w-5" />
                        {okCount} Belege OK
                    </span>
                    {hasErrors && (
                        <span className="flex items-center gap-1.5 text-amber-600">
                            <XCircle className="h-5 w-5" />
                            {errors.length} Fehler
                        </span>
                    )}
                </CardTitle>
            </CardHeader>
            <CardContent>
                {!hasErrors ? (
                    <p className="text-sm text-muted-foreground">
                        Alle Belege sind kontiert und exportierbar.
                    </p>
                ) : (
                    <>
                        <Button
                            variant="ghost"
                            size="sm"
                            className="h-auto px-2 py-1 text-sm"
                            onClick={() => setShowErrors((v) => !v)}
                            aria-expanded={showErrors}
                        >
                            {showErrors ? (
                                <ChevronDown className="mr-1 h-4 w-4" />
                            ) : (
                                <ChevronRight className="mr-1 h-4 w-4" />
                            )}
                            {errors.length} Belege werden übersprungen
                        </Button>

                        {showErrors && (
                            <ul className="mt-2 space-y-2">
                                {errors.map((item) => (
                                    <li
                                        key={item.document_id}
                                        className="flex flex-col gap-1 rounded-md border border-amber-100 bg-amber-50/50 p-2 text-sm sm:flex-row sm:items-center sm:justify-between"
                                    >
                                        <span className="font-medium">
                                            {item.filename ?? item.document_id}
                                        </span>
                                        <Badge
                                            variant="outline"
                                            className="w-fit border-amber-200 text-amber-700"
                                        >
                                            {item.reason ?? 'Keine gültige Kontierung'}
                                        </Badge>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </>
                )}
            </CardContent>
        </Card>
    );
}

export default ExportValidationSummary;
