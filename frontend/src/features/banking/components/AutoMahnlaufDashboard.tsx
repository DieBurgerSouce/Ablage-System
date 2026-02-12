/**
 * AutoMahnlaufDashboard - Automatischer Mahnlauf Dashboard
 *
 * Features:
 * - Vorschau der geplanten Mahnaktionen (Dry-Run)
 * - Einstellungen für den automatischen Mahnlauf
 * - Ausführung des Mahnlaufs mit Bestätigung
 * - Statistiken und Zusammenfassung
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
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
    Play,
    Settings,
    RefreshCw,
    Loader2,
    AlertTriangle,
    CheckCircle2,
    Clock,
    ArrowUpRight,
    Mail,
    Ban,
    Euro,
    Calendar,
    Save,
} from 'lucide-react';
import {
    useAutoDunningSettings,
    useUpdateAutoDunningSettings,
    useAutoDunningPreview,
    useProcessAutomaticDunning,
} from '../hooks/use-banking-queries';
import type { AutomaticDunningAction, AutoDunningSettings } from '@/lib/api/services/banking';
import { formatCurrency } from '../utils/format';
import { cn } from '@/lib/utils';

// ==================== Types ====================

type ActionType = 'escalate' | 'send_reminder' | 'create_task' | 'skip';

// ==================== Helper Functions ====================

const getActionIcon = (actionType: ActionType) => {
    switch (actionType) {
        case 'escalate':
            return <ArrowUpRight className="h-4 w-4 text-orange-500" />;
        case 'send_reminder':
            return <Mail className="h-4 w-4 text-blue-500" />;
        case 'create_task':
            return <Clock className="h-4 w-4 text-purple-500" />;
        case 'skip':
            return <Ban className="h-4 w-4 text-muted-foreground" />;
        default:
            return null;
    }
};

const getActionBadgeVariant = (actionType: ActionType): 'default' | 'secondary' | 'destructive' | 'outline' => {
    switch (actionType) {
        case 'escalate':
            return 'destructive';
        case 'send_reminder':
            return 'default';
        case 'create_task':
            return 'secondary';
        case 'skip':
            return 'outline';
        default:
            return 'outline';
    }
};

const getActionLabel = (actionType: ActionType): string => {
    switch (actionType) {
        case 'escalate':
            return 'Eskalieren';
        case 'send_reminder':
            return 'Erinnerung';
        case 'create_task':
            return 'Aufgabe';
        case 'skip':
            return 'Übersprungen';
        default:
            return actionType;
    }
};

// ==================== Preview Stats Card ====================

function PreviewStatsCard({ actions }: { actions: AutomaticDunningAction[] }) {
    const escalateCount = actions.filter(a => a.action_type === 'escalate').length;
    const reminderCount = actions.filter(a => a.action_type === 'send_reminder').length;
    const skippedCount = actions.filter(a => a.skipped).length;
    const totalAmount = actions
        .filter(a => !a.skipped)
        .reduce((sum, a) => sum + a.outstanding_amount, 0);

    return (
        <div className="grid gap-4 md:grid-cols-4">
            <Card>
                <CardContent className="pt-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-muted-foreground">Eskalationen</p>
                            <p className="text-2xl font-bold text-orange-500">{escalateCount}</p>
                        </div>
                        <ArrowUpRight className="h-8 w-8 text-orange-200" />
                    </div>
                </CardContent>
            </Card>
            <Card>
                <CardContent className="pt-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-muted-foreground">Erinnerungen</p>
                            <p className="text-2xl font-bold text-blue-500">{reminderCount}</p>
                        </div>
                        <Mail className="h-8 w-8 text-blue-200" />
                    </div>
                </CardContent>
            </Card>
            <Card>
                <CardContent className="pt-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-muted-foreground">Übersprungen</p>
                            <p className="text-2xl font-bold text-muted-foreground">{skippedCount}</p>
                        </div>
                        <Ban className="h-8 w-8 text-muted-foreground/30" />
                    </div>
                </CardContent>
            </Card>
            <Card>
                <CardContent className="pt-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-muted-foreground">Offener Betrag</p>
                            <p className="text-2xl font-bold">{formatCurrency(totalAmount)}</p>
                        </div>
                        <Euro className="h-8 w-8 text-green-200" />
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

// ==================== Preview Table ====================

function PreviewTable({
    actions,
    isLoading,
}: {
    actions: AutomaticDunningAction[];
    isLoading: boolean;
}) {
    if (isLoading) {
        return <Skeleton className="h-[400px] w-full" />;
    }

    if (actions.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-12 text-center">
                <CheckCircle2 className="h-12 w-12 text-green-500 mb-4" />
                <h3 className="text-lg font-semibold">Keine Aktionen erforderlich</h3>
                <p className="text-muted-foreground">
                    Aktuell gibt es keine Mahnvorgänge, die eskaliert werden müssen.
                </p>
            </div>
        );
    }

    return (
        <div className="rounded-md border">
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead>Rechnungsnr.</TableHead>
                        <TableHead>Schuldner</TableHead>
                        <TableHead className="text-center">Stufe</TableHead>
                        <TableHead className="text-right">Betrag</TableHead>
                        <TableHead className="text-right">Tage</TableHead>
                        <TableHead>Aktion</TableHead>
                        <TableHead>Beschreibung</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {actions.map((action) => (
                        <TableRow
                            key={action.dunning_id}
                            className={cn(action.skipped && 'opacity-50')}
                        >
                            <TableCell className="font-mono">
                                {action.invoice_number ?? '-'}
                            </TableCell>
                            <TableCell>
                                {action.debtor_name ?? 'Unbekannt'}
                            </TableCell>
                            <TableCell className="text-center">
                                <div className="flex items-center justify-center gap-1">
                                    <Badge variant="outline">{action.current_level}</Badge>
                                    {!action.skipped && (
                                        <>
                                            <span className="text-muted-foreground">→</span>
                                            <Badge variant="default">{action.new_level}</Badge>
                                        </>
                                    )}
                                </div>
                            </TableCell>
                            <TableCell className="text-right font-mono">
                                {formatCurrency(action.outstanding_amount)}
                            </TableCell>
                            <TableCell className="text-right">
                                <span className={cn(
                                    'font-medium',
                                    action.days_overdue > 30 && 'text-red-500',
                                    action.days_overdue > 14 && action.days_overdue <= 30 && 'text-orange-500',
                                )}>
                                    {action.days_overdue}
                                </span>
                            </TableCell>
                            <TableCell>
                                <Badge variant={getActionBadgeVariant(action.action_type)}>
                                    <span className="flex items-center gap-1">
                                        {getActionIcon(action.action_type)}
                                        {getActionLabel(action.action_type)}
                                    </span>
                                </Badge>
                            </TableCell>
                            <TableCell className="max-w-[200px] truncate text-sm text-muted-foreground">
                                {action.skipped ? action.skip_reason : action.action_description}
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </div>
    );
}

// ==================== Settings Card ====================

function SettingsCard({
    settings,
    isLoading,
    onSave,
    isSaving,
}: {
    settings: AutoDunningSettings | undefined;
    isLoading: boolean;
    onSave: (settings: Partial<AutoDunningSettings>) => void;
    isSaving: boolean;
}) {
    const [localSettings, setLocalSettings] = useState<Partial<AutoDunningSettings>>({});
    const [hasChanges, setHasChanges] = useState(false);

    // Sync local state when settings load
    const effectiveSettings = {
        enabled: localSettings.enabled ?? settings?.enabled ?? false,
        run_time: localSettings.run_time ?? settings?.run_time ?? '08:00',
        exclude_weekends: localSettings.exclude_weekends ?? settings?.exclude_weekends ?? true,
        exclude_holidays: localSettings.exclude_holidays ?? settings?.exclude_holidays ?? true,
        auto_send_email: localSettings.auto_send_email ?? settings?.auto_send_email ?? false,
        min_amount: localSettings.min_amount ?? settings?.min_amount ?? 10,
        max_auto_level: localSettings.max_auto_level ?? settings?.max_auto_level ?? 2,
        level_intervals: {
            level_1: localSettings.level_intervals?.level_1 ?? settings?.level_intervals?.level_1 ?? 7,
            level_2: localSettings.level_intervals?.level_2 ?? settings?.level_intervals?.level_2 ?? 14,
            level_3: localSettings.level_intervals?.level_3 ?? settings?.level_intervals?.level_3 ?? 21,
        },
    };

    const updateSetting = <K extends keyof AutoDunningSettings>(
        key: K,
        value: AutoDunningSettings[K]
    ) => {
        setLocalSettings(prev => ({ ...prev, [key]: value }));
        setHasChanges(true);
    };

    const handleSave = () => {
        onSave(localSettings);
        setHasChanges(false);
        setLocalSettings({});
    };

    if (isLoading) {
        return <Skeleton className="h-[400px] w-full" />;
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Settings className="h-5 w-5" />
                    Auto-Mahnlauf Einstellungen
                </CardTitle>
                <CardDescription>
                    Konfigurieren Sie den automatischen täglichen Mahnlauf
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                {/* Enable/Disable */}
                <div className="flex items-center justify-between p-4 border rounded-lg bg-muted/30">
                    <div className="space-y-1">
                        <Label className="text-base font-medium">Automatischer Mahnlauf</Label>
                        <p className="text-sm text-muted-foreground">
                            Mahnungen werden täglich automatisch verarbeitet
                        </p>
                    </div>
                    <Switch
                        checked={effectiveSettings.enabled}
                        onCheckedChange={(checked) => updateSetting('enabled', checked)}
                    />
                </div>

                <Separator />

                {/* Timing */}
                <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                        <Label htmlFor="run_time">
                            <Clock className="h-4 w-4 inline mr-1" />
                            Ausführungszeit
                        </Label>
                        <Input
                            id="run_time"
                            type="time"
                            value={effectiveSettings.run_time}
                            onChange={(e) => updateSetting('run_time', e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">
                            Täglicher Mahnlauf wird zu dieser Uhrzeit ausgeführt
                        </p>
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="min_amount">
                            <Euro className="h-4 w-4 inline mr-1" />
                            Mindestbetrag
                        </Label>
                        <Input
                            id="min_amount"
                            type="number"
                            min={0}
                            step={0.01}
                            value={effectiveSettings.min_amount}
                            onChange={(e) => updateSetting('min_amount', Number(e.target.value))}
                        />
                        <p className="text-xs text-muted-foreground">
                            Nur Rechnungen über diesem Betrag werden gemahnt
                        </p>
                    </div>
                </div>

                <Separator />

                {/* Exclusions */}
                <div className="space-y-4">
                    <h4 className="text-sm font-medium">Ausnahmen</h4>
                    <div className="flex items-center justify-between">
                        <div className="space-y-1">
                            <Label>Wochenenden ausschließen</Label>
                            <p className="text-xs text-muted-foreground">
                                Kein Mahnlauf an Samstagen und Sonntagen
                            </p>
                        </div>
                        <Switch
                            checked={effectiveSettings.exclude_weekends}
                            onCheckedChange={(checked) => updateSetting('exclude_weekends', checked)}
                        />
                    </div>
                    <div className="flex items-center justify-between">
                        <div className="space-y-1">
                            <Label>Feiertage ausschließen</Label>
                            <p className="text-xs text-muted-foreground">
                                Deutsche Feiertage werden automatisch übersprungen
                            </p>
                        </div>
                        <Switch
                            checked={effectiveSettings.exclude_holidays}
                            onCheckedChange={(checked) => updateSetting('exclude_holidays', checked)}
                        />
                    </div>
                </div>

                <Separator />

                {/* Intervals */}
                <div className="space-y-4">
                    <h4 className="text-sm font-medium flex items-center gap-2">
                        <Calendar className="h-4 w-4" />
                        Mahnintervalle (Tage nach Fälligkeit)
                    </h4>
                    <div className="grid gap-4 md:grid-cols-3">
                        <div className="space-y-2">
                            <Label htmlFor="level_1">1. Mahnung</Label>
                            <Input
                                id="level_1"
                                type="number"
                                min={1}
                                max={90}
                                value={effectiveSettings.level_intervals.level_1}
                                onChange={(e) => updateSetting('level_intervals', {
                                    ...effectiveSettings.level_intervals,
                                    level_1: Number(e.target.value),
                                })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="level_2">2. Mahnung</Label>
                            <Input
                                id="level_2"
                                type="number"
                                min={1}
                                max={90}
                                value={effectiveSettings.level_intervals.level_2}
                                onChange={(e) => updateSetting('level_intervals', {
                                    ...effectiveSettings.level_intervals,
                                    level_2: Number(e.target.value),
                                })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="level_3">3. Mahnung</Label>
                            <Input
                                id="level_3"
                                type="number"
                                min={1}
                                max={90}
                                value={effectiveSettings.level_intervals.level_3}
                                onChange={(e) => updateSetting('level_intervals', {
                                    ...effectiveSettings.level_intervals,
                                    level_3: Number(e.target.value),
                                })}
                            />
                        </div>
                    </div>
                </div>

                <Separator />

                {/* Email Automation */}
                <div className="flex items-center justify-between p-4 border rounded-lg border-orange-200 bg-orange-50/50">
                    <div className="space-y-1">
                        <Label className="flex items-center gap-2">
                            <Mail className="h-4 w-4" />
                            Automatischer E-Mail-Versand
                        </Label>
                        <p className="text-xs text-muted-foreground">
                            Mahnungen werden automatisch per E-Mail versendet (Opt-in)
                        </p>
                    </div>
                    <Switch
                        checked={effectiveSettings.auto_send_email}
                        onCheckedChange={(checked) => updateSetting('auto_send_email', checked)}
                    />
                </div>

                {/* Save Button */}
                {hasChanges && (
                    <div className="flex justify-end pt-4">
                        <Button onClick={handleSave} disabled={isSaving}>
                            {isSaving ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <Save className="h-4 w-4 mr-2" />
                            )}
                            Einstellungen speichern
                        </Button>
                    </div>
                )}

                {/* Status Info */}
                {settings?.last_run_at && (
                    <div className="text-xs text-muted-foreground text-right pt-2">
                        Letzter Mahnlauf: {new Date(settings.last_run_at).toLocaleString('de-DE')}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

// ==================== Main Component ====================

export function AutoMahnlaufDashboard() {
    const { toast } = useToast();
    const [showConfirmDialog, setShowConfirmDialog] = useState(false);

    // Queries
    const { data: settings, isLoading: settingsLoading } = useAutoDunningSettings();
    const { data: preview, isLoading: previewLoading, refetch: refetchPreview } = useAutoDunningPreview();

    // Mutations
    const updateSettings = useUpdateAutoDunningSettings();
    const processAutoDunning = useProcessAutomaticDunning();

    const handleSaveSettings = async (newSettings: Partial<AutoDunningSettings>) => {
        try {
            await updateSettings.mutateAsync(newSettings);
            toast({ title: 'Einstellungen gespeichert' });
        } catch {
            toast({
                title: 'Fehler beim Speichern',
                description: 'Die Einstellungen konnten nicht gespeichert werden.',
                variant: 'destructive',
            });
        }
    };

    const handleExecuteMahnlauf = async () => {
        setShowConfirmDialog(false);
        try {
            const result = await processAutoDunning.mutateAsync(false);
            const executed = result.filter((a: AutomaticDunningAction) => !a.skipped).length;
            toast({
                title: 'Mahnlauf ausgeführt',
                description: `${executed} Mahnung(en) wurden verarbeitet.`,
            });
            refetchPreview();
        } catch {
            toast({
                title: 'Fehler beim Mahnlauf',
                description: 'Der Mahnlauf konnte nicht ausgeführt werden.',
                variant: 'destructive',
            });
        }
    };

    const actionsToExecute = preview?.filter(a => !a.skipped) ?? [];

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold">Automatischer Mahnlauf</h2>
                    <p className="text-muted-foreground">
                        Vorschau und Ausführung des automatischen Mahnverfahrens
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button
                        variant="outline"
                        onClick={() => refetchPreview()}
                        disabled={previewLoading}
                    >
                        <RefreshCw className={cn('h-4 w-4 mr-2', previewLoading && 'animate-spin')} />
                        Aktualisieren
                    </Button>
                    <Button
                        onClick={() => setShowConfirmDialog(true)}
                        disabled={actionsToExecute.length === 0 || processAutoDunning.isPending}
                    >
                        {processAutoDunning.isPending ? (
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                            <Play className="h-4 w-4 mr-2" />
                        )}
                        Mahnlauf ausführen
                    </Button>
                </div>
            </div>

            {/* Stats */}
            <PreviewStatsCard actions={preview ?? []} />

            {/* Preview Table */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <AlertTriangle className="h-5 w-5 text-orange-500" />
                        Vorschau: Geplante Aktionen
                    </CardTitle>
                    <CardDescription>
                        Diese Aktionen werden beim nächsten Mahnlauf ausgeführt
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <PreviewTable
                        actions={preview ?? []}
                        isLoading={previewLoading}
                    />
                </CardContent>
            </Card>

            {/* Settings */}
            <SettingsCard
                settings={settings}
                isLoading={settingsLoading}
                onSave={handleSaveSettings}
                isSaving={updateSettings.isPending}
            />

            {/* Confirmation Dialog */}
            <AlertDialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Mahnlauf ausführen?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Es werden <strong>{actionsToExecute.length}</strong> Mahnaktionen ausgeführt.
                            Dieser Vorgang kann nicht rückgängig gemacht werden.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction onClick={handleExecuteMahnlauf}>
                            Mahnlauf starten
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}
