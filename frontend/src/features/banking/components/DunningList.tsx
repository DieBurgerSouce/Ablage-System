/**
 * Dunning List Komponente
 * Zeigt ueberfaellige Rechnungen mit Mahnempfehlungen
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/components/ui/use-toast';
import {
    AlertTriangle,
    Mail,
    FileWarning,
    Gavel,
    ExternalLink,
    ChevronRight,
} from 'lucide-react';
import { useOverdueInvoices, useDunningStats, useCreateDunning } from '../hooks/use-banking-queries';
import { cn } from '@/lib/utils';
import { formatCurrency, formatDate } from '../utils/format';

const LEVEL_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive'; icon: React.ReactNode }> = {
    'not_started': {
        label: 'Nicht begonnen',
        variant: 'outline',
        icon: null,
    },
    'first_reminder': {
        label: '1. Mahnung',
        variant: 'secondary',
        icon: <Mail className="h-3 w-3" />,
    },
    'second_reminder': {
        label: '2. Mahnung',
        variant: 'secondary',
        icon: <FileWarning className="h-3 w-3" />,
    },
    'final_reminder': {
        label: 'Letzte Mahnung',
        variant: 'destructive',
        icon: <AlertTriangle className="h-3 w-3" />,
    },
};

const ACTION_CONFIG: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
    'reminder': {
        label: 'Erinnerung senden',
        icon: <Mail className="h-4 w-4" />,
        color: 'text-blue-600',
    },
    'first_dunning': {
        label: '1. Mahnung',
        icon: <Mail className="h-4 w-4" />,
        color: 'text-yellow-600',
    },
    'second_dunning': {
        label: '2. Mahnung',
        icon: <FileWarning className="h-4 w-4" />,
        color: 'text-orange-600',
    },
    'final_dunning': {
        label: 'Letzte Mahnung',
        icon: <AlertTriangle className="h-4 w-4" />,
        color: 'text-red-600',
    },
    'collection': {
        label: 'Inkasso',
        icon: <Gavel className="h-4 w-4" />,
        color: 'text-red-700',
    },
};

function LevelBadge({ level }: { level: string }) {
    const config = LEVEL_CONFIG[level] ?? LEVEL_CONFIG['not_started'];
    return (
        <Badge variant={config.variant} className="gap-1">
            {config.icon}
            {config.label}
        </Badge>
    );
}

function ActionButton({
    action,
    documentId,
    invoiceNumber,
    onAction
}: {
    action: string;
    documentId: string;
    invoiceNumber?: string;
    onAction: (documentId: string, action: string, label: string, invoiceNumber?: string) => void;
}) {
    const config = ACTION_CONFIG[action] ?? ACTION_CONFIG['reminder'];

    return (
        <Button
            variant="outline"
            size="sm"
            className={cn('gap-1', config.color)}
            onClick={() => onAction(documentId, action, config.label, invoiceNumber)}
        >
            {config.icon}
            {config.label}
            <ChevronRight className="h-3 w-3" />
        </Button>
    );
}

interface PendingAction {
    documentId: string;
    level: string;
    actionLabel: string;
    invoiceNumber?: string;
}

export function DunningList() {
    const { toast } = useToast();
    const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);

    const { data: overdueInvoices, isLoading: invoicesLoading, error: invoicesError } = useOverdueInvoices({ min_days: 1 });
    const { data: stats, isLoading: statsLoading } = useDunningStats();

    const createDunning = useCreateDunning();
    // TODO: Implement escalation UI using useEscalateDunning()

    const isLoading = invoicesLoading || statsLoading;

    const handleActionClick = (documentId: string, level: string, actionLabel: string, invoiceNumber?: string) => {
        // Fuer kritische Aktionen (Inkasso, letzte Mahnung) Bestätigung anfordern
        const criticalActions = ['final_dunning', 'collection'];
        const levelMap: Record<string, string> = {
            'reminder': 'not_started',
            'first_dunning': 'first_reminder',
            'second_dunning': 'second_reminder',
            'final_dunning': 'final_reminder',
            'collection': 'final_reminder',
        };
        const mappedLevel = levelMap[level] ?? 'first_reminder';

        if (criticalActions.includes(level)) {
            setPendingAction({ documentId, level: mappedLevel, actionLabel, invoiceNumber });
        } else {
            executeAction(documentId, mappedLevel, actionLabel);
        }
    };

    const executeAction = (documentId: string, level: string, actionLabel: string) => {
        createDunning.mutate(
            { document_id: documentId, level },
            {
                onSuccess: () => {
                    toast({
                        title: 'Mahnung erstellt',
                        description: `${actionLabel} wurde erfolgreich erstellt.`,
                    });
                },
                onError: (error: Error) => {
                    toast({
                        title: 'Fehler',
                        description: error.message || 'Die Mahnung konnte nicht erstellt werden.',
                        variant: 'destructive',
                    });
                },
            }
        );
    };

    const confirmAction = () => {
        if (pendingAction) {
            executeAction(pendingAction.documentId, pendingAction.level, pendingAction.actionLabel);
            setPendingAction(null);
        }
    };

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <Skeleton className="h-6 w-32" />
                    <Skeleton className="h-4 w-64" />
                </CardHeader>
                <CardContent>
                    <Skeleton className="h-[400px] w-full" />
                </CardContent>
            </Card>
        );
    }

    if (invoicesError || !overdueInvoices) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Mahnwesen</CardTitle>
                    <CardDescription className="text-destructive">
                        Fehler beim Laden der Daten
                    </CardDescription>
                </CardHeader>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Stats Summary */}
            {stats && (
                <div className="grid gap-4 md:grid-cols-4">
                    <Card>
                        <CardContent className="pt-6">
                            <div className="text-2xl font-bold">{stats.total_active}</div>
                            <p className="text-sm text-muted-foreground">Aktive Mahnungen</p>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <div className="text-2xl font-bold">{formatCurrency(stats.total_amount_overdue)}</div>
                            <p className="text-sm text-muted-foreground">Überfälliger Betrag</p>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <div className="text-2xl font-bold">{formatCurrency(stats.total_fees)}</div>
                            <p className="text-sm text-muted-foreground">Mahngebühren</p>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <div className="text-2xl font-bold">{Math.round(stats.avg_days_overdue)} Tage</div>
                            <p className="text-sm text-muted-foreground">Ø Überfälligkeit</p>
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Overdue Invoices Table */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <AlertTriangle className="h-5 w-5 text-destructive" />
                        Überfällige Rechnungen
                    </CardTitle>
                    <CardDescription>
                        {overdueInvoices.length} Rechnungen erfordern Maßnahmen
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="rounded-md border overflow-x-auto">
                        <Table className="min-w-[900px]">
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Rechnung</TableHead>
                                    <TableHead>Debitor</TableHead>
                                    <TableHead className="text-right">Betrag</TableHead>
                                    <TableHead>Fälligkeit</TableHead>
                                    <TableHead className="text-right">Tage</TableHead>
                                    <TableHead>Mahnstufe</TableHead>
                                    <TableHead className="text-right">Gesamt</TableHead>
                                    <TableHead>Empfehlung</TableHead>
                                    <TableHead className="w-[50px]"></TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {overdueInvoices.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={9} className="text-center text-muted-foreground py-8">
                                            Keine überfälligen Rechnungen
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    overdueInvoices.map((invoice) => (
                                        <TableRow key={invoice.document_id}>
                                            <TableCell className="font-medium">
                                                {invoice.invoice_number || '-'}
                                            </TableCell>
                                            <TableCell>{invoice.creditor_name || '-'}</TableCell>
                                            <TableCell className="text-right font-mono">
                                                {formatCurrency(invoice.amount)}
                                            </TableCell>
                                            <TableCell>{formatDate(invoice.due_date)}</TableCell>
                                            <TableCell className="text-right">
                                                <span className="text-destructive font-medium">
                                                    +{invoice.days_overdue}
                                                </span>
                                            </TableCell>
                                            <TableCell>
                                                <LevelBadge level={invoice.current_level} />
                                            </TableCell>
                                            <TableCell className="text-right font-mono">
                                                <div className="text-sm">
                                                    {formatCurrency(invoice.total_due)}
                                                </div>
                                                {(invoice.accumulated_fees > 0 || invoice.late_interest > 0) && (
                                                    <div className="text-xs text-muted-foreground">
                                                        +{formatCurrency(invoice.accumulated_fees + invoice.late_interest)}
                                                    </div>
                                                )}
                                            </TableCell>
                                            <TableCell>
                                                <ActionButton
                                                    action={invoice.recommended_action}
                                                    documentId={invoice.document_id}
                                                    invoiceNumber={invoice.invoice_number}
                                                    onAction={handleActionClick}
                                                />
                                            </TableCell>
                                            <TableCell>
                                                <Button variant="ghost" size="icon" asChild>
                                                    <a href={`/documents/${invoice.document_id}`} target="_blank" rel="noopener">
                                                        <ExternalLink className="h-4 w-4" />
                                                    </a>
                                                </Button>
                                            </TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </div>
                </CardContent>
            </Card>

            {/* Bestätigungsdialog für kritische Aktionen */}
            <AlertDialog open={!!pendingAction} onOpenChange={(open) => !open && setPendingAction(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Mahnung bestätigen</AlertDialogTitle>
                        <AlertDialogDescription>
                            Möchten Sie wirklich "{pendingAction?.actionLabel}" für
                            {pendingAction?.invoiceNumber
                                ? ` Rechnung ${pendingAction.invoiceNumber}`
                                : ' diese Rechnung'
                            } ausführen?
                            {pendingAction?.level === 'final_reminder' && (
                                <span className="block mt-2 text-destructive font-medium">
                                    Dies ist eine kritische Aktion und kann rechtliche Konsequenzen haben.
                                </span>
                            )}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={confirmAction}
                            className={pendingAction?.level === 'final_reminder' ? 'bg-destructive hover:bg-destructive/90' : ''}
                        >
                            Bestätigen
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}
