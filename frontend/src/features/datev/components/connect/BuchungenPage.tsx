/**
 * DATEV Connect - Buchungen-Verwaltung
 *
 * Listet alle Buchungen auf mit Festschreibungs-Funktionalitaet.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Checkbox } from '@/components/ui/checkbox';
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
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Lock,
    Unlock,
    ShieldCheck,
    AlertTriangle,
    FileText,
    RefreshCw,
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import {
    useConnections,
    useBuchungen,
    useFestschreiben,
    useComplianceReport,
} from '@/features/datev/hooks/use-datev-connect-queries';
import type { DATEVBuchungResponse } from '@/lib/api/services/datev-connect';

export function BuchungenPage() {
    const { data: connections, isLoading: connectionsLoading } = useConnections();
    const [selectedConnectionId, setSelectedConnectionId] = useState<string>('');
    const [selectedBuchungen, setSelectedBuchungen] = useState<Set<string>>(new Set());
    const [showFestschreibenDialog, setShowFestschreibenDialog] = useState(false);
    const [festschreibenAll, setFestschreibenAll] = useState(false);

    const { toast } = useToast();

    // Aktive Verbindung

    // Buchungen laden
    const {
        data: buchungenData,
        isLoading: buchungenLoading,
        refetch: refetchBuchungen,
    } = useBuchungen(selectedConnectionId, { page_size: 50 }, !!selectedConnectionId);

    // Compliance Report
    const { data: complianceReport } = useComplianceReport(selectedConnectionId, !!selectedConnectionId);

    // Festschreiben Mutation
    const festschreiben = useFestschreiben();

    // Auto-select erste Verbindung
    if (!selectedConnectionId && connections && connections.length > 0) {
        const connected = connections.find((c) => c.status === 'connected');
        if (connected) {
            setSelectedConnectionId(connected.id);
        }
    }

    const handleSelectAll = (checked: boolean) => {
        if (checked && buchungenData) {
            const pendingIds = buchungenData.items
                .filter((b) => !b.ist_festgeschrieben)
                .map((b) => b.id);
            setSelectedBuchungen(new Set(pendingIds));
        } else {
            setSelectedBuchungen(new Set());
        }
    };

    const handleSelectOne = (buchungId: string, checked: boolean) => {
        const newSet = new Set(selectedBuchungen);
        if (checked) {
            newSet.add(buchungId);
        } else {
            newSet.delete(buchungId);
        }
        setSelectedBuchungen(newSet);
    };

    const handleFestschreiben = async () => {
        if (!selectedConnectionId) return;

        try {
            const result = await festschreiben.mutateAsync({
                connectionId: selectedConnectionId,
                data: festschreibenAll
                    ? { all_pending: true }
                    : { buchung_ids: Array.from(selectedBuchungen) },
            });

            toast({
                title: 'Buchungen festgeschrieben',
                description: `${result.festgeschrieben_count} Buchungen wurden GoBD-konform festgeschrieben.`,
            });

            setSelectedBuchungen(new Set());
            setShowFestschreibenDialog(false);
            refetchBuchungen();
        } catch {
            toast({
                title: 'Festschreiben fehlgeschlagen',
                description: 'Die Buchungen konnten nicht festgeschrieben werden.',
                variant: 'destructive',
            });
        }
    };

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('de-DE', {
            style: 'currency',
            currency: 'EUR',
        }).format(amount);
    };

    const pendingBuchungen = buchungenData?.items.filter((b) => !b.ist_festgeschrieben) || [];

    return (
        <div className="space-y-6">
            {/* Header mit Verbindungsauswahl */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h2 className="text-xl font-semibold">Buchungen</h2>
                    <p className="text-sm text-muted-foreground">
                        Verwalten und festschreiben Sie Ihre DATEV-Buchungen.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Select
                        value={selectedConnectionId || 'none'}
                        onValueChange={(value) => {
                            if (value !== 'none') {
                                setSelectedConnectionId(value);
                                setSelectedBuchungen(new Set());
                            }
                        }}
                    >
                        <SelectTrigger className="w-[250px]">
                            <SelectValue placeholder="Verbindung wählen..." />
                        </SelectTrigger>
                        <SelectContent>
                            {connectionsLoading ? (
                                <SelectItem value="none" disabled>
                                    Lade...
                                </SelectItem>
                            ) : !connections || connections.length === 0 ? (
                                <SelectItem value="none" disabled>
                                    Keine Verbindungen
                                </SelectItem>
                            ) : (
                                connections
                                    .filter((c) => c.status === 'connected')
                                    .map((conn) => (
                                        <SelectItem key={conn.id} value={conn.id}>
                                            {conn.name} ({conn.mandant_nr})
                                        </SelectItem>
                                    ))
                            )}
                        </SelectContent>
                    </Select>
                    <Button
                        variant="outline"
                        size="icon"
                        onClick={() => refetchBuchungen()}
                        disabled={!selectedConnectionId || buchungenLoading}
                    >
                        <RefreshCw className={`h-4 w-4 ${buchungenLoading ? 'animate-spin' : ''}`} />
                    </Button>
                </div>
            </div>

            {/* Compliance Status Card */}
            {complianceReport && (
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="text-base flex items-center gap-2">
                            <ShieldCheck className="h-5 w-5 text-green-600" />
                            GoBD Compliance Status
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div>
                                <p className="text-sm text-muted-foreground">Gesamt</p>
                                <p className="text-2xl font-bold">{complianceReport.total_buchungen}</p>
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">Festgeschrieben</p>
                                <p className="text-2xl font-bold text-green-600">
                                    {complianceReport.festgeschrieben_count}
                                </p>
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">Ausstehend</p>
                                <p className="text-2xl font-bold text-yellow-600">
                                    {complianceReport.pending_count}
                                </p>
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">Integritätsprobleme</p>
                                <p className="text-2xl font-bold text-red-600">
                                    {complianceReport.integrity_check.failed}
                                </p>
                            </div>
                        </div>
                        {complianceReport.integrity_check.issues.length > 0 && (
                            <div className="mt-4 p-3 bg-red-50 dark:bg-red-950 rounded-md">
                                <div className="flex items-center gap-2 text-red-600 mb-2">
                                    <AlertTriangle className="h-4 w-4" />
                                    <span className="font-medium">Integritätsprobleme erkannt</span>
                                </div>
                                <ul className="text-sm text-red-600 space-y-1">
                                    {complianceReport.integrity_check.issues.slice(0, 3).map((issue) => (
                                        <li key={issue.buchung_id}>
                                            Buchung #{issue.buchungs_nr}: {issue.issue}
                                        </li>
                                    ))}
                                    {complianceReport.integrity_check.issues.length > 3 && (
                                        <li>
                                            ... und {complianceReport.integrity_check.issues.length - 3} weitere
                                        </li>
                                    )}
                                </ul>
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Buchungen-Tabelle */}
            <Card>
                <CardHeader>
                    <div className="flex justify-between items-center">
                        <div>
                            <CardTitle className="text-base">Buchungsliste</CardTitle>
                            <CardDescription>
                                {buchungenLoading
                                    ? 'Lade...'
                                    : `${buchungenData?.total || 0} Buchungen • ${pendingBuchungen.length} ausstehend`}
                            </CardDescription>
                        </div>
                        {pendingBuchungen.length > 0 && (
                            <div className="flex gap-2">
                                <Button
                                    variant="outline"
                                    onClick={() => {
                                        setFestschreibenAll(false);
                                        setShowFestschreibenDialog(true);
                                    }}
                                    disabled={selectedBuchungen.size === 0}
                                >
                                    <Lock className="mr-2 h-4 w-4" />
                                    Ausgewaehlte festschreiben ({selectedBuchungen.size})
                                </Button>
                                <Button
                                    onClick={() => {
                                        setFestschreibenAll(true);
                                        setShowFestschreibenDialog(true);
                                    }}
                                >
                                    <Lock className="mr-2 h-4 w-4" />
                                    Alle festschreiben
                                </Button>
                            </div>
                        )}
                    </div>
                </CardHeader>
                <CardContent>
                    {!selectedConnectionId ? (
                        <div className="text-center py-10">
                            <FileText className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                            <p className="text-muted-foreground">
                                Wählen Sie eine Verbindung aus, um Buchungen anzuzeigen.
                            </p>
                        </div>
                    ) : buchungenLoading ? (
                        <div className="space-y-3">
                            {[1, 2, 3, 4, 5].map((i) => (
                                <Skeleton key={i} className="h-12 w-full" />
                            ))}
                        </div>
                    ) : !buchungenData || buchungenData.items.length === 0 ? (
                        <div className="text-center py-10">
                            <FileText className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                            <p className="text-muted-foreground">
                                Keine Buchungen vorhanden.
                            </p>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-[50px]">
                                        <Checkbox
                                            checked={
                                                pendingBuchungen.length > 0 &&
                                                selectedBuchungen.size === pendingBuchungen.length
                                            }
                                            onCheckedChange={handleSelectAll}
                                            disabled={pendingBuchungen.length === 0}
                                        />
                                    </TableHead>
                                    <TableHead>Nr.</TableHead>
                                    <TableHead>Datum</TableHead>
                                    <TableHead>Soll</TableHead>
                                    <TableHead>Haben</TableHead>
                                    <TableHead className="text-right">Betrag</TableHead>
                                    <TableHead>Buchungstext</TableHead>
                                    <TableHead>Status</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {buchungenData.items.map((buchung) => (
                                    <BuchungRow
                                        key={buchung.id}
                                        buchung={buchung}
                                        isSelected={selectedBuchungen.has(buchung.id)}
                                        onSelect={handleSelectOne}
                                        formatCurrency={formatCurrency}
                                    />
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>

            {/* Festschreiben Dialog */}
            <AlertDialog open={showFestschreibenDialog} onOpenChange={setShowFestschreibenDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle className="flex items-center gap-2">
                            <Lock className="h-5 w-5" />
                            Buchungen festschreiben?
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            {festschreibenAll ? (
                                <>
                                    Möchten Sie <strong>alle {pendingBuchungen.length} ausstehenden Buchungen</strong>{' '}
                                    GoBD-konform festschreiben?
                                </>
                            ) : (
                                <>
                                    Möchten Sie <strong>{selectedBuchungen.size} ausgewählte Buchungen</strong>{' '}
                                    GoBD-konform festschreiben?
                                </>
                            )}
                            <br />
                            <br />
                            <strong>Achtung:</strong> Festgeschriebene Buchungen können nicht mehr geändert
                            oder gelöscht werden. Diese Aktion ist unwiderruflich und dient der GoBD-Compliance.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleFestschreiben}
                            className="bg-green-600 hover:bg-green-700"
                        >
                            <Lock className="mr-2 h-4 w-4" />
                            Festschreiben
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}

// =============================================================================
// BUCHUNG ROW COMPONENT
// =============================================================================

interface BuchungRowProps {
    buchung: DATEVBuchungResponse;
    isSelected: boolean;
    onSelect: (id: string, checked: boolean) => void;
    formatCurrency: (amount: number) => string;
}

function BuchungRow({ buchung, isSelected, onSelect, formatCurrency }: BuchungRowProps) {
    return (
        <TableRow>
            <TableCell>
                <Checkbox
                    checked={isSelected}
                    onCheckedChange={(checked) => onSelect(buchung.id, !!checked)}
                    disabled={buchung.ist_festgeschrieben}
                />
            </TableCell>
            <TableCell className="font-mono">
                {buchung.buchungs_nr || '–'}
            </TableCell>
            <TableCell>
                {new Date(buchung.belegdatum).toLocaleDateString('de-DE')}
            </TableCell>
            <TableCell className="font-mono">{buchung.konto_soll}</TableCell>
            <TableCell className="font-mono">{buchung.konto_haben}</TableCell>
            <TableCell className="text-right font-mono">
                {formatCurrency(buchung.betrag)}
            </TableCell>
            <TableCell className="max-w-[200px] truncate">
                {buchung.buchungstext}
            </TableCell>
            <TableCell>
                {buchung.ist_festgeschrieben ? (
                    <Badge className="bg-green-100 text-green-800">
                        <Lock className="h-3 w-3 mr-1" />
                        Festgeschrieben
                    </Badge>
                ) : (
                    <Badge variant="secondary">
                        <Unlock className="h-3 w-3 mr-1" />
                        Ausstehend
                    </Badge>
                )}
            </TableCell>
        </TableRow>
    );
}
