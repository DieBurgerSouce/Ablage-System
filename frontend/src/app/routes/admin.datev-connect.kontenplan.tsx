/**
 * DATEV Connect - Kontenplan Route
 */

import { useState } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
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
import { Search, BookOpen } from 'lucide-react';
import { useConnections, useKontenplan } from '@/features/datev/hooks/use-datev-connect-queries';

export const Route = createFileRoute('/admin/datev-connect/kontenplan')({
    component: KontenplanPage,
});

function KontenplanPage() {
    const { data: connections, isLoading: connectionsLoading } = useConnections();
    const [selectedConnectionId, setSelectedConnectionId] = useState<string>('');
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedKategorie, setSelectedKategorie] = useState<string>('all');

    // Auto-select erste verbundene Verbindung
    if (!selectedConnectionId && connections && connections.length > 0) {
        const connected = connections.find((c) => c.status === 'connected');
        if (connected) {
            setSelectedConnectionId(connected.id);
        }
    }

    const { data: kontenplan, isLoading: kontenplanLoading } = useKontenplan(
        selectedConnectionId,
        { search: searchTerm || undefined, kategorie: selectedKategorie !== 'all' ? selectedKategorie : undefined },
        !!selectedConnectionId
    );

    // Alle einzigartigen Kategorien extrahieren
    const kategorien = kontenplan?.items
        ? [...new Set(kontenplan.items.map((k) => k.kategorie))].sort()
        : [];

    // Konten filtern
    const filteredKonten = kontenplan?.items.filter((konto) => {
        const matchesSearch =
            !searchTerm ||
            konto.kontonummer.includes(searchTerm) ||
            konto.bezeichnung.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesKategorie =
            selectedKategorie === 'all' || konto.kategorie === selectedKategorie;
        return matchesSearch && matchesKategorie;
    }) || [];

    const formatCurrency = (amount: number | null) => {
        if (amount === null) return '–';
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
                    <h2 className="text-xl font-semibold">Kontenplan</h2>
                    <p className="text-sm text-muted-foreground">
                        DATEV-Kontenrahmen mit aktuellen Salden.
                    </p>
                </div>
                <Select
                    value={selectedConnectionId || 'none'}
                    onValueChange={(value) => {
                        if (value !== 'none') {
                            setSelectedConnectionId(value);
                        }
                    }}
                >
                    <SelectTrigger className="w-[250px]">
                        <SelectValue placeholder="Verbindung waehlen..." />
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
                                        {conn.name} ({conn.kontenrahmen})
                                    </SelectItem>
                                ))
                        )}
                    </SelectContent>
                </Select>
            </div>

            {/* Info Card */}
            {kontenplan && (
                <Card>
                    <CardContent className="py-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <BookOpen className="h-5 w-5 text-muted-foreground" />
                                <div>
                                    <p className="text-sm font-medium">
                                        Kontenrahmen {kontenplan.kontenrahmen}
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                        Stand: {new Date(kontenplan.stand).toLocaleDateString('de-DE')}
                                    </p>
                                </div>
                            </div>
                            <Badge variant="outline">{kontenplan.total} Konten</Badge>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Filter */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-base">Filter</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-col sm:flex-row gap-4">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input
                                placeholder="Konto oder Bezeichnung suchen..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="pl-9"
                            />
                        </div>
                        <Select value={selectedKategorie} onValueChange={setSelectedKategorie}>
                            <SelectTrigger className="w-[200px]">
                                <SelectValue placeholder="Kategorie..." />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Alle Kategorien</SelectItem>
                                {kategorien.map((kat) => (
                                    <SelectItem key={kat} value={kat}>
                                        {kat}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                </CardContent>
            </Card>

            {/* Konten-Tabelle */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Kontenliste</CardTitle>
                    <CardDescription>
                        {kontenplanLoading
                            ? 'Lade...'
                            : `${filteredKonten.length} von ${kontenplan?.total || 0} Konten`}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {!selectedConnectionId ? (
                        <div className="text-center py-10">
                            <BookOpen className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                            <p className="text-muted-foreground">
                                Waehlen Sie eine Verbindung aus, um den Kontenplan anzuzeigen.
                            </p>
                        </div>
                    ) : kontenplanLoading ? (
                        <div className="space-y-3">
                            {[1, 2, 3, 4, 5].map((i) => (
                                <Skeleton key={i} className="h-12 w-full" />
                            ))}
                        </div>
                    ) : filteredKonten.length === 0 ? (
                        <div className="text-center py-10">
                            <Search className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                            <p className="text-muted-foreground">
                                Keine Konten gefunden.
                            </p>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-[100px]">Konto</TableHead>
                                    <TableHead>Bezeichnung</TableHead>
                                    <TableHead>Kategorie</TableHead>
                                    <TableHead className="text-right">Saldo</TableHead>
                                    <TableHead>Letzte Buchung</TableHead>
                                    <TableHead>Status</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {filteredKonten.map((konto) => (
                                    <TableRow key={konto.id}>
                                        <TableCell className="font-mono font-medium">
                                            {konto.kontonummer}
                                        </TableCell>
                                        <TableCell>{konto.bezeichnung}</TableCell>
                                        <TableCell>
                                            <Badge variant="outline">{konto.kategorie}</Badge>
                                        </TableCell>
                                        <TableCell className="text-right font-mono">
                                            {formatCurrency(konto.saldo)}
                                        </TableCell>
                                        <TableCell className="text-muted-foreground">
                                            {konto.letzte_buchung
                                                ? new Date(konto.letzte_buchung).toLocaleDateString('de-DE')
                                                : '–'}
                                        </TableCell>
                                        <TableCell>
                                            {konto.ist_aktiv ? (
                                                <Badge className="bg-green-100 text-green-800">Aktiv</Badge>
                                            ) : (
                                                <Badge variant="secondary">Inaktiv</Badge>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
