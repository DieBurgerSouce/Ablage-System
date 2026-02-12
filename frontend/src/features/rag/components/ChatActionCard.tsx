/**
 * Chat Action Card Component
 *
 * Zeigt eine Tool-Aktion im Chat an mit Bestätigung/Ablehnung.
 */

import { memo } from 'react';
import { motion } from 'framer-motion';
import {
    CheckCircle,
    XCircle,
    Loader2,
    AlertTriangle,
    Wrench,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { ChatToolAction } from '../types/chat-types';

interface ChatActionCardProps {
    action: ChatToolAction;
    onConfirm: (actionId: string) => void;
    onReject: (actionId: string) => void;
    isConfirming?: boolean;
}

// German tool name labels
const toolLabels: Record<string, string> = {
    search_documents: 'Dokumente durchsuchen',
    move_document: 'Dokument verschieben',
    tag_document: 'Tags hinzufügen',
    get_invoice_status: 'Rechnungsstatus abfragen',
    filter_documents: 'Dokumente filtern',
    get_entity_summary: 'Geschäftspartner-Zusammenfassung',
    categorize_document: 'Dokument kategorisieren',
    create_reminder: 'Erinnerung erstellen',
    get_daily_agenda: 'Tagesplanung',
    compare_expenses: 'Ausgabenvergleich',
    book_invoice: 'Rechnung buchen',
    approve_document: 'Dokument genehmigen',
    get_skonto_opportunities: 'Skonto-Möglichkeiten',
    get_overdue_invoices: 'Überfällige Rechnungen',
};

/**
 * Get German label for tool name.
 */
function getToolLabel(toolName: string): string {
    return toolLabels[toolName] || toolName;
}

/**
 * Format parameters for display.
 */
function formatParameters(parameters: Record<string, unknown>): string {
    return Object.entries(parameters)
        .map(([key, value]) => {
            let displayValue = String(value);
            if (typeof value === 'object' && value !== null) {
                displayValue = JSON.stringify(value);
            }
            return `${key}: ${displayValue}`;
        })
        .join(', ');
}

/**
 * Format result for display.
 */
function formatResult(result: Record<string, unknown>): string {
    if (result.message) {
        return String(result.message);
    }
    if (result.success) {
        return 'Erfolgreich ausgeführt';
    }
    return JSON.stringify(result);
}

export const ChatActionCard = memo(function ChatActionCard({
    action,
    onConfirm,
    onReject,
    isConfirming = false,
}: ChatActionCardProps) {
    const isPending = action.status === 'pending_confirmation';
    const isConfirmed = action.status === 'confirmed';
    const isExecuted = action.status === 'executed';
    const isRejected = action.status === 'rejected';
    const isFailed = action.status === 'failed';

    // Determine card styling
    const cardClassName = cn(
        'border-l-4',
        isPending && 'border-l-yellow-500',
        isConfirmed && 'border-l-blue-500',
        isExecuted && 'border-l-green-500',
        isRejected && 'border-l-gray-400',
        isFailed && 'border-l-red-500'
    );

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.2 }}
        >
            <Card className={cardClassName}>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                        <Wrench className="h-4 w-4" />
                        {getToolLabel(action.tool_name)}

                        {/* Status Badge */}
                        {isExecuted && (
                            <Badge variant="default" className="ml-auto bg-green-500">
                                <CheckCircle className="h-3 w-3 mr-1" />
                                Ausgeführt
                            </Badge>
                        )}
                        {isRejected && (
                            <Badge variant="secondary" className="ml-auto">
                                Abgelehnt
                            </Badge>
                        )}
                        {isFailed && (
                            <Badge variant="destructive" className="ml-auto">
                                <AlertTriangle className="h-3 w-3 mr-1" />
                                Fehler
                            </Badge>
                        )}
                        {(isConfirmed || isConfirming) && (
                            <Badge variant="secondary" className="ml-auto">
                                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                                Wird ausgeführt...
                            </Badge>
                        )}
                    </CardTitle>
                </CardHeader>

                <CardContent className="space-y-3">
                    {/* Description */}
                    {action.description && (
                        <p className="text-sm text-muted-foreground">
                            {action.description}
                        </p>
                    )}

                    {/* Parameters */}
                    {Object.keys(action.parameters).length > 0 && (
                        <div className="text-xs">
                            <span className="font-medium">Parameter: </span>
                            <span className="text-muted-foreground">
                                {formatParameters(action.parameters)}
                            </span>
                        </div>
                    )}

                    {/* Success Result */}
                    {isExecuted && action.result && (
                        <div className="flex items-start gap-2 p-3 bg-green-50 dark:bg-green-950/20 rounded-md border border-green-200 dark:border-green-800">
                            <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                            <div className="text-sm text-green-800 dark:text-green-200">
                                {formatResult(action.result)}
                            </div>
                        </div>
                    )}

                    {/* Error Message */}
                    {isFailed && action.error_message && (
                        <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-950/20 rounded-md border border-red-200 dark:border-red-800">
                            <XCircle className="h-4 w-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                            <div className="text-sm text-red-800 dark:text-red-200">
                                {action.error_message}
                            </div>
                        </div>
                    )}

                    {/* Action Buttons */}
                    {isPending && action.requires_confirmation && (
                        <div className="flex gap-2 pt-2">
                            <Button
                                size="sm"
                                onClick={() => onConfirm(action.action_id)}
                                disabled={isConfirming}
                                className="flex-1"
                            >
                                {isConfirming ? (
                                    <>
                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                        Wird ausgeführt...
                                    </>
                                ) : (
                                    <>
                                        <CheckCircle className="h-4 w-4 mr-2" />
                                        Ausführen
                                    </>
                                )}
                            </Button>
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={() => onReject(action.action_id)}
                                disabled={isConfirming}
                                className="flex-1"
                            >
                                <XCircle className="h-4 w-4 mr-2" />
                                Ablehnen
                            </Button>
                        </div>
                    )}
                </CardContent>
            </Card>
        </motion.div>
    );
});

export default ChatActionCard;
