/**
 * DATEV Connect - Kontierungsvorschläge
 *
 * ML-gestützte Kontierungsvorschläge mit Lernfunktion.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Brain,
    CheckCircle,
    XCircle,
    Pencil,
    Sparkles,
    RefreshCw,
    GraduationCap,
    TrendingUp,
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import {
    useConnections,
    useKontenplan,
    useAcceptKontierung,
    useRejectKontierung,
    useLearnKontierung,
    useKontierungsvorschlaege,
} from '@/features/datev/hooks/use-datev-connect-queries';
import { formatConfidence, type DATEVKontierungStatus } from '@/lib/api/services/datev-connect';

/**
 * Kontierungsvorschlag mit optionalen Dokumentinformationen
 */
interface KontierungVorschlag {
    id: string;
    document_id: string;
    connection_id: string;
    konto_soll: string;
    konto_soll_bezeichnung: string;
    konto_haben: string;
    konto_haben_bezeichnung: string;
    steuerschluessel: string | null;
    kostenstelle: string | null;
    confidence: number;
    status: DATEVKontierungStatus;
    pattern_id: string | null;
    created_at: string;
    document_info?: {
        filename: string;
        lieferant: string;
        betrag: number;
    };
}

export function KontierungPage() {
    const { data: connections, isLoading: connectionsLoading } = useConnections();
    const [selectedConnectionId, setSelectedConnectionId] = useState<string>('');
    const [editDialog, setEditDialog] = useState<KontierungVorschlag | null>(null);
    const [learnDialog, setLearnDialog] = useState(false);
    const [learnData, setLearnData] = useState({
        lieferant: '',
        konto_soll: '',
        konto_haben: '',
        steuerschluessel: '',
    });

    const { toast } = useToast();

    // Kontenplan für Auswahl
    const { data: kontenplan } = useKontenplan(selectedConnectionId, undefined, !!selectedConnectionId);

    const acceptKontierung = useAcceptKontierung();
    const rejectKontierung = useRejectKontierung();
    const learnKontierung = useLearnKontierung();

    // Auto-select erste verbundene Verbindung
    if (!selectedConnectionId && connections && connections.length > 0) {
        const connected = connections.find((c) => c.status === 'connected');
        if (connected) {
            setSelectedConnectionId(connected.id);
        }
    }

    // Kontierungsvorschlaege von API laden
    const { data: vorschlaege = [], isLoading: vorschlaegeLoading } = useKontierungsvorschlaege(
        selectedConnectionId,
        !!selectedConnectionId
    );

    const handleAccept = async (vorschlag: KontierungVorschlag) => {
        try {
            await acceptKontierung.mutateAsync({
                connectionId: vorschlag.connection_id,
                vorschlagId: vorschlag.id,
            });
            toast({
                title: 'Kontierung akzeptiert',
                description: 'Die Buchung wurde erstellt.',
            });
        } catch {
            toast({
                title: 'Fehler',
                description: 'Die Kontierung konnte nicht akzeptiert werden.',
                variant: 'destructive',
            });
        }
    };

    const handleReject = async (vorschlag: KontierungVorschlag) => {
        try {
            await rejectKontierung.mutateAsync({
                connectionId: vorschlag.connection_id,
                vorschlagId: vorschlag.id,
            });
            toast({
                title: 'Kontierung abgelehnt',
                description: 'Der Vorschlag wurde verworfen.',
            });
        } catch {
            toast({
                title: 'Fehler',
                description: 'Die Kontierung konnte nicht abgelehnt werden.',
                variant: 'destructive',
            });
        }
    };

    const handleAcceptWithChanges = async () => {
        if (!editDialog) return;

        try {
            await acceptKontierung.mutateAsync({
                connectionId: editDialog.connection_id,
                vorschlagId: editDialog.id,
                data: {
                    konto_soll: editDialog.konto_soll,
                    konto_haben: editDialog.konto_haben,
                    steuerschluessel: editDialog.steuerschluessel || undefined,
                },
            });
            setEditDialog(null);
            toast({
                title: 'Kontierung übernommen',
                description: 'Die Buchung wurde mit Ihren Änderungen erstellt.',
            });
        } catch {
            toast({
                title: 'Fehler',
                description: 'Die Kontierung konnte nicht übernommen werden.',
                variant: 'destructive',
            });
        }
    };

    const handleLearn = async () => {
        if (!selectedConnectionId) return;

        try {
            await learnKontierung.mutateAsync({
                connectionId: selectedConnectionId,
                data: {
                    document_id: 'manual',
                    lieferant_name: learnData.lieferant,
                    konto_soll: learnData.konto_soll,
                    konto_haben: learnData.konto_haben,
                    steuerschluessel: learnData.steuerschluessel || undefined,
                },
            });
            setLearnDialog(false);
            setLearnData({ lieferant: '', konto_soll: '', konto_haben: '', steuerschluessel: '' });
            toast({
                title: 'Muster gelernt',
                description: 'Das neue Kontierungsmuster wurde gespeichert.',
            });
        } catch {
            toast({
                title: 'Fehler',
                description: 'Das Muster konnte nicht gelernt werden.',
                variant: 'destructive',
            });
        }
    };

    const getConfidenceBadge = (confidence: number) => {
        if (confidence >= 0.9) {
            return <Badge className="bg-green-100 text-green-800">{formatConfidence(confidence)}</Badge>;
        } else if (confidence >= 0.7) {
            return <Badge className="bg-yellow-100 text-yellow-800">{formatConfidence(confidence)}</Badge>;
        } else {
            return <Badge className="bg-orange-100 text-orange-800">{formatConfidence(confidence)}</Badge>;
        }
    };

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('de-DE', {
            style: 'currency',
            currency: 'EUR',
        }).format(amount);
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h2 className="text-xl font-semibold flex items-center gap-2">
                        <Brain className="h-6 w-6 text-purple-600" />
                        KI-Kontierungsvorschläge
                    </h2>
                    <p className="text-sm text-muted-foreground">
                        ML-gestützte Kontierungsvorschläge mit automatischem Lernen.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Select
                        value={selectedConnectionId || 'none'}
                        onValueChange={(value) => {
                            if (value !== 'none') {
                                setSelectedConnectionId(value);
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
                                            {conn.name}
                                        </SelectItem>
                                    ))
                            )}
                        </SelectContent>
                    </Select>
                    <Button variant="outline" onClick={() => setLearnDialog(true)}>
                        <GraduationCap className="mr-2 h-4 w-4" />
                        Muster lernen
                    </Button>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="grid gap-4 md:grid-cols-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium">Ausstehend</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{vorschlaege.length}</div>
                        <p className="text-xs text-muted-foreground">Vorschläge zur Prüfung</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium">Hohe Konfidenz</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-green-600">
                            {vorschlaege.filter((v) => v.confidence >= 0.9).length}
                        </div>
                        <p className="text-xs text-muted-foreground">{'>'} 90% Sicherheit</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium">Gelernte Muster</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-purple-600">47</div>
                        <p className="text-xs text-muted-foreground">Aktive Kontierungsregeln</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium">Akzeptanzrate</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold flex items-center gap-1">
                            <TrendingUp className="h-5 w-5 text-green-600" />
                            87%
                        </div>
                        <p className="text-xs text-muted-foreground">Letzte 30 Tage</p>
                    </CardContent>
                </Card>
            </div>

            {/* Vorschläge-Tabelle */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                        <Sparkles className="h-5 w-5 text-yellow-500" />
                        Aktuelle Vorschläge
                    </CardTitle>
                    <CardDescription>
                        Prüfen und bestätigen Sie die KI-generierten Kontierungen.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {!selectedConnectionId ? (
                        <div className="text-center py-10">
                            <Brain className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                            <p className="text-muted-foreground">
                                Wählen Sie eine Verbindung aus, um Vorschläge anzuzeigen.
                            </p>
                        </div>
                    ) : vorschlaegeLoading ? (
                        <div className="space-y-3 py-4">
                            {[1, 2, 3].map((i) => (
                                <Skeleton key={i} className="h-16 w-full" />
                            ))}
                        </div>
                    ) : vorschlaege.length === 0 ? (
                        <div className="text-center py-10">
                            <CheckCircle className="h-12 w-12 mx-auto text-green-500 mb-4" />
                            <p className="text-muted-foreground">
                                Alle Kontierungen wurden verarbeitet.
                            </p>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Dokument</TableHead>
                                    <TableHead>Lieferant</TableHead>
                                    <TableHead className="text-right">Betrag</TableHead>
                                    <TableHead>Soll</TableHead>
                                    <TableHead>Haben</TableHead>
                                    <TableHead>Konfidenz</TableHead>
                                    <TableHead className="text-right">Aktionen</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {vorschlaege.map((vorschlag) => (
                                    <TableRow key={vorschlag.id}>
                                        <TableCell className="font-medium max-w-[200px] truncate">
                                            {vorschlag.document_info?.filename ?? 'Unbekannt'}
                                        </TableCell>
                                        <TableCell>{vorschlag.document_info?.lieferant ?? '-'}</TableCell>
                                        <TableCell className="text-right font-mono">
                                            {vorschlag.document_info?.betrag != null
                                                ? formatCurrency(vorschlag.document_info.betrag)
                                                : '-'}
                                        </TableCell>
                                        <TableCell>
                                            <div>
                                                <span className="font-mono">{vorschlag.konto_soll}</span>
                                                <p className="text-xs text-muted-foreground">
                                                    {vorschlag.konto_soll_bezeichnung}
                                                </p>
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            <div>
                                                <span className="font-mono">{vorschlag.konto_haben}</span>
                                                <p className="text-xs text-muted-foreground">
                                                    {vorschlag.konto_haben_bezeichnung}
                                                </p>
                                            </div>
                                        </TableCell>
                                        <TableCell>{getConfidenceBadge(vorschlag.confidence)}</TableCell>
                                        <TableCell className="text-right">
                                            <div className="flex justify-end gap-1">
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    className="text-green-600 hover:text-green-700 hover:bg-green-50"
                                                    onClick={() => handleAccept(vorschlag)}
                                                >
                                                    <CheckCircle className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    onClick={() => setEditDialog(vorschlag)}
                                                >
                                                    <Pencil className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                                                    onClick={() => handleReject(vorschlag)}
                                                >
                                                    <XCircle className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>

            {/* Edit Dialog */}
            <Dialog open={!!editDialog} onOpenChange={() => setEditDialog(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Kontierung bearbeiten</DialogTitle>
                        <DialogDescription>
                            Passen Sie die vorgeschlagene Kontierung an.
                        </DialogDescription>
                    </DialogHeader>
                    {editDialog && (
                        <div className="space-y-4">
                            <div className="p-3 bg-muted rounded-md">
                                <p className="text-sm font-medium">
                                    {editDialog.document_info?.filename ?? 'Unbekannt'}
                                </p>
                                <p className="text-sm text-muted-foreground">
                                    {editDialog.document_info?.lieferant ?? '-'}
                                    {editDialog.document_info?.betrag != null && (
                                        <> • {formatCurrency(editDialog.document_info.betrag)}</>
                                    )}
                                </p>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>Soll-Konto</Label>
                                    <Input
                                        value={editDialog.konto_soll}
                                        onChange={(e) =>
                                            setEditDialog({ ...editDialog, konto_soll: e.target.value })
                                        }
                                        className="font-mono"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Haben-Konto</Label>
                                    <Input
                                        value={editDialog.konto_haben}
                                        onChange={(e) =>
                                            setEditDialog({ ...editDialog, konto_haben: e.target.value })
                                        }
                                        className="font-mono"
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <Label>Steuerschlüssel</Label>
                                <Input
                                    value={editDialog.steuerschluessel || ''}
                                    onChange={(e) =>
                                        setEditDialog({ ...editDialog, steuerschluessel: e.target.value })
                                    }
                                    placeholder="z.B. 19"
                                />
                            </div>
                        </div>
                    )}
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setEditDialog(null)}>
                            Abbrechen
                        </Button>
                        <Button onClick={handleAcceptWithChanges}>
                            <CheckCircle className="mr-2 h-4 w-4" />
                            Übernehmen
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Learn Dialog */}
            <Dialog open={learnDialog} onOpenChange={setLearnDialog}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <GraduationCap className="h-5 w-5" />
                            Neues Kontierungsmuster
                        </DialogTitle>
                        <DialogDescription>
                            Bringen Sie dem System ein neues Kontierungsmuster bei.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label>Lieferant</Label>
                            <Input
                                value={learnData.lieferant}
                                onChange={(e) =>
                                    setLearnData({ ...learnData, lieferant: e.target.value })
                                }
                                placeholder="z.B. Amazon EU S.a.r.l."
                            />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Soll-Konto</Label>
                                <Input
                                    value={learnData.konto_soll}
                                    onChange={(e) =>
                                        setLearnData({ ...learnData, konto_soll: e.target.value })
                                    }
                                    placeholder="z.B. 4400"
                                    className="font-mono"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Haben-Konto</Label>
                                <Input
                                    value={learnData.konto_haben}
                                    onChange={(e) =>
                                        setLearnData({ ...learnData, konto_haben: e.target.value })
                                    }
                                    placeholder="z.B. 70000"
                                    className="font-mono"
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label>Steuerschlüssel (optional)</Label>
                            <Input
                                value={learnData.steuerschluessel}
                                onChange={(e) =>
                                    setLearnData({ ...learnData, steuerschluessel: e.target.value })
                                }
                                placeholder="z.B. 19"
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setLearnDialog(false)}>
                            Abbrechen
                        </Button>
                        <Button
                            onClick={handleLearn}
                            disabled={!learnData.lieferant || !learnData.konto_soll || !learnData.konto_haben}
                        >
                            <GraduationCap className="mr-2 h-4 w-4" />
                            Muster speichern
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
