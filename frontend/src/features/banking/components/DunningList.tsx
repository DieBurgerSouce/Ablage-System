/**
 * Dunning List Komponente (Aktualisiert)
 *
 * Vollstaendige Mahnungsverwaltung mit:
 * - DunningTable mit TanStack Table
 * - BulkActionsBar fuer Massenaktionen
 * - MahnungDetailSheet fuer Details
 * - TelefonProtokollDialog fuer Anrufprotokolle
 */

import { useState, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
    TrendingUp,
    Building2,
    User,
    PauseCircle,
    RefreshCw,
} from 'lucide-react';
import {
    useDunningRecords,
    useDunningStats,
    useEscalateDunning,
} from '../hooks/use-banking-queries';
import type { DunningRecord } from '@/lib/api/services/banking';
import { formatCurrency } from '../utils/format';

// Sub-components
import { DunningTable } from './DunningTable';
import { BulkActionsBar } from './BulkActionsBar';
import { MahnungDetailSheet } from './MahnungDetailSheet';
import { TelefonProtokollDialog } from './TelefonProtokollDialog';

// ==================== Stats Cards ====================

function StatsCards({ stats, isLoading }: {
    stats?: {
        total_active: number;
        total_amount_overdue: number;
        total_fees: number;
        avg_days_overdue: number;
        by_level?: Record<number, number>;
        b2b_count?: number;
        b2c_count?: number;
        mahnstopp_count?: number;
    };
    isLoading: boolean;
}) {
    if (isLoading) {
        return (
            <div className="grid gap-4 md:grid-cols-4">
                {[1, 2, 3, 4].map((i) => (
                    <Card key={i}>
                        <CardContent className="pt-6">
                            <Skeleton className="h-8 w-24 mb-2" />
                            <Skeleton className="h-4 w-32" />
                        </CardContent>
                    </Card>
                ))}
            </div>
        );
    }

    if (!stats) return null;

    return (
        <div className="grid gap-4 md:grid-cols-4 lg:grid-cols-5">
            <Card>
                <CardContent className="pt-6">
                    <div className="text-2xl font-bold">{stats.total_active}</div>
                    <p className="text-sm text-muted-foreground">Aktive Mahnungen</p>
                </CardContent>
            </Card>
            <Card>
                <CardContent className="pt-6">
                    <div className="text-2xl font-bold text-destructive">
                        {formatCurrency(stats.total_amount_overdue)}
                    </div>
                    <p className="text-sm text-muted-foreground">Offene Forderungen</p>
                </CardContent>
            </Card>
            <Card>
                <CardContent className="pt-6">
                    <div className="text-2xl font-bold text-green-600">
                        {formatCurrency(stats.total_fees)}
                    </div>
                    <p className="text-sm text-muted-foreground">Mahngebuehren</p>
                </CardContent>
            </Card>
            <Card>
                <CardContent className="pt-6">
                    <div className="text-2xl font-bold">
                        {Math.round(stats.avg_days_overdue)} Tage
                    </div>
                    <p className="text-sm text-muted-foreground">Ø Ueberfaelligkeit</p>
                </CardContent>
            </Card>
            <Card>
                <CardContent className="pt-6">
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-1">
                            <Building2 className="h-4 w-4 text-blue-600" />
                            <span className="font-bold">{stats.b2b_count ?? 0}</span>
                        </div>
                        <div className="flex items-center gap-1">
                            <User className="h-4 w-4 text-gray-600" />
                            <span className="font-bold">{stats.b2c_count ?? 0}</span>
                        </div>
                        {(stats.mahnstopp_count ?? 0) > 0 && (
                            <div className="flex items-center gap-1">
                                <PauseCircle className="h-4 w-4 text-orange-600" />
                                <span className="font-bold">{stats.mahnstopp_count}</span>
                            </div>
                        )}
                    </div>
                    <p className="text-sm text-muted-foreground">B2B / B2C / Mahnstopp</p>
                </CardContent>
            </Card>
        </div>
    );
}

// ==================== Main Component ====================

export function DunningList() {
    // Toast Hook
    const { toast } = useToast();

    // State
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    const [selectedDunning, setSelectedDunning] = useState<DunningRecord | null>(null);
    const [detailSheetOpen, setDetailSheetOpen] = useState(false);
    const [phoneDialogOpen, setPhoneDialogOpen] = useState(false);
    const [escalateDialogOpen, setEscalateDialogOpen] = useState(false);
    const [activeTab, setActiveTab] = useState<'all' | 'active' | 'mahnstopp'>('active');

    // Queries
    const queryResult = useDunningRecords({
        status: activeTab === 'mahnstopp' ? undefined : activeTab === 'active' ? 'active' : undefined,
        mahnstopp: activeTab === 'mahnstopp' ? true : undefined,
    });
    const dunningRecords = queryResult.data as { items: DunningRecord[]; total: number } | undefined;
    const recordsLoading = queryResult.isLoading;
    const recordsError = queryResult.error;
    const refetchRecords = queryResult.refetch;

    const { data: stats, isLoading: statsLoading } = useDunningStats();

    // Mutations
    const escalateDunning = useEscalateDunning();

    // Handlers
    const handleRowClick = useCallback((dunning: DunningRecord) => {
        setSelectedDunning(dunning);
        setDetailSheetOpen(true);
    }, []);

    const handleSelectionChange = useCallback((ids: string[]) => {
        setSelectedIds(ids);
    }, []);

    const handleClearSelection = useCallback(() => {
        setSelectedIds([]);
    }, []);

    const handleActionComplete = useCallback(() => {
        refetchRecords();
    }, [refetchRecords]);

    const handleLogPhoneCall = useCallback(() => {
        if (selectedDunning) {
            setPhoneDialogOpen(true);
        }
    }, [selectedDunning]);

    const handleEscalate = useCallback(() => {
        if (selectedDunning) {
            setEscalateDialogOpen(true);
        }
    }, [selectedDunning]);

    const confirmEscalate = async () => {
        if (!selectedDunning) return;

        try {
            await escalateDunning.mutateAsync(selectedDunning.id);
            toast({
                title: 'Mahnung eskaliert',
                description: `Mahnvorgang ${selectedDunning.invoice_number} wurde auf die naechste Stufe eskaliert.`,
            });
            setEscalateDialogOpen(false);
            refetchRecords();
        } catch {
            toast({
                variant: 'destructive',
                title: 'Eskalation fehlgeschlagen',
                description: 'Der Mahnvorgang konnte nicht eskaliert werden.',
            });
        }
    };

    // Filter data based on tab
    const filteredRecords = dunningRecords?.items ?? [];

    // Loading state
    if (recordsLoading && !dunningRecords?.items) {
        return (
            <div className="space-y-6">
                <StatsCards stats={undefined} isLoading={true} />
                <Card>
                    <CardHeader>
                        <Skeleton className="h-6 w-48" />
                        <Skeleton className="h-4 w-64" />
                    </CardHeader>
                    <CardContent>
                        <Skeleton className="h-[400px] w-full" />
                    </CardContent>
                </Card>
            </div>
        );
    }

    // Error state
    if (recordsError) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-destructive">
                        <AlertTriangle className="h-5 w-5" />
                        Fehler beim Laden
                    </CardTitle>
                    <CardDescription>
                        Die Mahnungsdaten konnten nicht geladen werden. Bitte versuchen Sie es erneut.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Button onClick={() => refetchRecords()} variant="outline">
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Erneut versuchen
                    </Button>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Stats Summary */}
            <StatsCards stats={stats} isLoading={statsLoading} />

            {/* Bulk Actions Bar (shows when items are selected) */}
            <BulkActionsBar
                selectedIds={selectedIds}
                onClearSelection={handleClearSelection}
                onActionComplete={handleActionComplete}
            />

            {/* Main Content Card */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <AlertTriangle className="h-5 w-5 text-destructive" />
                                Mahnungsverwaltung
                            </CardTitle>
                            <CardDescription>
                                {filteredRecords.length} Mahnvorgaenge
                                {selectedIds.length > 0 && (
                                    <Badge variant="secondary" className="ml-2">
                                        {selectedIds.length} ausgewaehlt
                                    </Badge>
                                )}
                            </CardDescription>
                        </div>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => refetchRecords()}
                            disabled={recordsLoading}
                        >
                            <RefreshCw className={`h-4 w-4 mr-2 ${recordsLoading ? 'animate-spin' : ''}`} />
                            Aktualisieren
                        </Button>
                    </div>
                </CardHeader>

                <CardContent>
                    <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
                        <TabsList className="mb-4">
                            <TabsTrigger value="active">
                                Aktiv
                                {stats && (
                                    <Badge variant="secondary" className="ml-1.5">
                                        {stats.total_active}
                                    </Badge>
                                )}
                            </TabsTrigger>
                            <TabsTrigger value="mahnstopp">
                                <PauseCircle className="h-4 w-4 mr-1" />
                                Mahnstopp
                                {stats?.mahnstopp_count && stats.mahnstopp_count > 0 && (
                                    <Badge variant="outline" className="ml-1.5 border-orange-500 text-orange-600">
                                        {stats.mahnstopp_count}
                                    </Badge>
                                )}
                            </TabsTrigger>
                            <TabsTrigger value="all">Alle</TabsTrigger>
                        </TabsList>

                        <TabsContent value={activeTab} className="mt-0">
                            <DunningTable
                                data={filteredRecords}
                                isLoading={recordsLoading}
                                onRowClick={handleRowClick}
                                onSelectionChange={handleSelectionChange}
                            />
                        </TabsContent>
                    </Tabs>
                </CardContent>
            </Card>

            {/* Detail Sheet */}
            <MahnungDetailSheet
                dunning={selectedDunning}
                open={detailSheetOpen}
                onOpenChange={setDetailSheetOpen}
                onLogPhoneCall={handleLogPhoneCall}
                onEscalate={handleEscalate}
            />

            {/* Phone Call Dialog */}
            <TelefonProtokollDialog
                dunningId={selectedDunning?.id ?? ''}
                debtorName={selectedDunning?.debtor_name ?? undefined}
                open={phoneDialogOpen}
                onOpenChange={setPhoneDialogOpen}
                onSuccess={handleActionComplete}
            />

            {/* Escalation Confirmation Dialog */}
            <AlertDialog open={escalateDialogOpen} onOpenChange={setEscalateDialogOpen}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle className="flex items-center gap-2">
                            <TrendingUp className="h-5 w-5 text-orange-600" />
                            Mahnung eskalieren?
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            Moechten Sie den Mahnvorgang{' '}
                            <span className="font-medium">
                                {selectedDunning?.invoice_number}
                            </span>{' '}
                            auf die naechste Mahnstufe eskalieren?
                            <br /><br />
                            <span className="text-muted-foreground">
                                Aktuelle Stufe: {selectedDunning?.dunning_level ?? 0}
                                {' → '}
                                Neue Stufe: {(selectedDunning?.dunning_level ?? 0) + 1}
                            </span>
                            {selectedDunning?.dunning_level && selectedDunning.dunning_level >= 3 && (
                                <span className="block mt-2 text-destructive font-medium">
                                    Achtung: Ab Stufe 4 wird die letzte Mahnung vor Inkasso versendet.
                                </span>
                            )}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={confirmEscalate}
                            className="bg-orange-600 hover:bg-orange-700"
                            disabled={escalateDunning.isPending}
                        >
                            <TrendingUp className="h-4 w-4 mr-2" />
                            Eskalieren
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}
