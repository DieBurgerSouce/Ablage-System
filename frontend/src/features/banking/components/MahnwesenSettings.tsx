/**
 * MahnwesenSettings - Konfiguration des Mahnwesens
 *
 * Features:
 * - Mahnstufen-Konfiguration (Tage, Gebühren, Kommunikationskanal)
 * - Basiszins-Verwaltung (aktuell 2.27% ab Januar 2025)
 * - B2B/B2C Einstellungen
 * - Automatisierungsregeln
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
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
    Settings,
    Euro,
    Mail,
    Phone,
    Edit,
    Building2,
    User,
    Info,
    Save,
    Loader2,
    Clock,
} from 'lucide-react';
import { Link } from '@tanstack/react-router';
import {
    useDunningStageConfigs,
    useUpdateDunningStageConfig,
    useAutoDunningSettings,
    useUpdateAutoDunningSettings,
} from '../hooks/use-banking-queries';
import type { DunningStageConfig } from '@/types/models/banking';
import { formatCurrency } from '../utils/format';

// ==================== Configuration ====================

const CHANNEL_OPTIONS = [
    { value: 'email', label: 'E-Mail', icon: <Mail className="h-4 w-4" /> },
    { value: 'letter', label: 'Brief', icon: <Mail className="h-4 w-4" /> },
    { value: 'phone', label: 'Telefonat', icon: <Phone className="h-4 w-4" /> },
    { value: 'none', label: 'Keine Kommunikation', icon: null },
];

const STAGE_LABELS: Record<number, string> = {
    0: 'Neu (Verzug eingetreten)',
    1: 'Zahlungserinnerung',
    2: '1. Mahnung',
    3: '2. Mahnung',
    4: 'Letzte Mahnung',
    5: 'Inkasso',
};

// ==================== Basiszins Info Card ====================

function BasiszinsInfoCard() {
    return (
        <Card className="border-blue-200 bg-blue-50/50">
            <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center gap-2">
                    <Euro className="h-4 w-4" />
                    Basiszinssatz (Stand: Januar 2025)
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-3">
                    <div>
                        <div className="text-xs text-muted-foreground">Basiszins</div>
                        <div className="text-2xl font-bold">2,27%</div>
                    </div>
                    <div>
                        <div className="text-xs text-muted-foreground flex items-center gap-1">
                            <Building2 className="h-3 w-3" /> B2B (+9%)
                        </div>
                        <div className="text-2xl font-bold text-blue-600">11,27% p.a.</div>
                    </div>
                    <div>
                        <div className="text-xs text-muted-foreground flex items-center gap-1">
                            <User className="h-3 w-3" /> B2C (+5%)
                        </div>
                        <div className="text-2xl font-bold">7,27% p.a.</div>
                    </div>
                </div>
                <div className="text-xs text-muted-foreground flex items-center gap-1">
                    <Info className="h-3 w-3" />
                    Quelle: Deutsche Bundesbank, §247 BGB
                </div>
            </CardContent>
        </Card>
    );
}

// ==================== B2B Settings Card ====================

function B2BSettingsCard() {
    const [b2bPauschale, setB2bPauschale] = useState(40);
    const [autoClaimPauschale, setAutoClaimPauschale] = useState(true);

    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                    <Building2 className="h-4 w-4" />
                    B2B-Einstellungen (§288 Abs. 5 BGB)
                </CardTitle>
                <CardDescription>
                    Pauschale und Sonderregeln für Geschäftskunden
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                        <Label htmlFor="pauschale">Pauschalbetrag (€)</Label>
                        <Input
                            id="pauschale"
                            type="number"
                            value={b2bPauschale}
                            onChange={(e) => setB2bPauschale(Number(e.target.value))}
                            min={0}
                        />
                        <p className="text-xs text-muted-foreground">
                            Gesetzlich festgelegt: 40,00 €
                        </p>
                    </div>
                    <div className="flex items-center justify-between space-x-4 p-4 border rounded-lg">
                        <div className="space-y-1">
                            <Label>Pauschale automatisch beanspruchen</Label>
                            <p className="text-xs text-muted-foreground">
                                Bei Verzug automatisch zur Forderung hinzufügen
                            </p>
                        </div>
                        <Switch
                            checked={autoClaimPauschale}
                            onCheckedChange={setAutoClaimPauschale}
                        />
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

// ==================== Automation Settings Card ====================

function AutomationSettingsCard() {
    const { toast } = useToast();
    const { data: settings, isLoading } = useAutoDunningSettings();
    const updateSettings = useUpdateAutoDunningSettings();

    const handleToggle = async (key: string, value: boolean) => {
        try {
            await updateSettings.mutateAsync({ [key]: value });
            toast({ title: 'Einstellung gespeichert' });
        } catch {
            toast({ title: 'Fehler beim Speichern', variant: 'destructive' });
        }
    };

    const handleTimeChange = async (value: string) => {
        try {
            await updateSettings.mutateAsync({ run_time: value });
            toast({ title: 'Uhrzeit gespeichert' });
        } catch {
            toast({ title: 'Fehler beim Speichern', variant: 'destructive' });
        }
    };

    if (isLoading) {
        return <Skeleton className="h-[300px] w-full" />;
    }

    return (
        <Card>
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-sm flex items-center gap-2">
                            <Clock className="h-4 w-4" />
                            Automatisierung
                        </CardTitle>
                        <CardDescription>
                            Einstellungen für den täglichen automatischen Mahnlauf
                        </CardDescription>
                    </div>
                    <Link to="/banking/auto-mahnlauf">
                        <Button variant="outline" size="sm">
                            Mahnlauf-Dashboard
                        </Button>
                    </Link>
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="flex items-center justify-between p-4 border rounded-lg bg-muted/30">
                    <div className="space-y-1">
                        <Label className="text-base font-medium">Automatischer Mahnlauf</Label>
                        <p className="text-sm text-muted-foreground">
                            Mahnungen werden täglich automatisch verarbeitet
                        </p>
                    </div>
                    <Switch
                        checked={settings?.enabled ?? false}
                        onCheckedChange={(checked) => handleToggle('enabled', checked)}
                        disabled={updateSettings.isPending}
                    />
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                        <Label htmlFor="mahnlauf-time">Mahnlauf-Uhrzeit</Label>
                        <Input
                            id="mahnlauf-time"
                            type="time"
                            value={settings?.run_time ?? '08:00'}
                            onChange={(e) => handleTimeChange(e.target.value)}
                            disabled={updateSettings.isPending}
                        />
                        <p className="text-xs text-muted-foreground">
                            Wann der tägliche Mahnlauf ausgeführt wird
                        </p>
                    </div>
                </div>

                <Separator />

                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="space-y-1">
                            <Label>Wochenenden ausschließen</Label>
                            <p className="text-xs text-muted-foreground">
                                Kein Mahnlauf an Samstagen und Sonntagen
                            </p>
                        </div>
                        <Switch
                            checked={settings?.exclude_weekends ?? true}
                            onCheckedChange={(checked) => handleToggle('exclude_weekends', checked)}
                            disabled={updateSettings.isPending}
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
                            checked={settings?.exclude_holidays ?? true}
                            onCheckedChange={(checked) => handleToggle('exclude_holidays', checked)}
                            disabled={updateSettings.isPending}
                        />
                    </div>

                    <div className="flex items-center justify-between">
                        <div className="space-y-1">
                            <Label>Automatischer E-Mail-Versand</Label>
                            <p className="text-xs text-muted-foreground">
                                Mahnungen automatisch per E-Mail versenden (Opt-in)
                            </p>
                        </div>
                        <Switch
                            checked={settings?.auto_send_email ?? false}
                            onCheckedChange={(checked) => handleToggle('auto_send_email', checked)}
                            disabled={updateSettings.isPending}
                        />
                    </div>
                </div>

                {settings?.last_run_at && (
                    <div className="text-xs text-muted-foreground text-right pt-2">
                        Letzter Mahnlauf: {new Date(settings.last_run_at).toLocaleString('de-DE')}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

// ==================== Stage Config Table ====================

function StageConfigTable({
    configs,
    isLoading,
    onEdit,
}: {
    configs: DunningStageConfig[];
    isLoading: boolean;
    onEdit: (config: DunningStageConfig) => void;
}) {
    if (isLoading) {
        return <Skeleton className="h-[300px] w-full" />;
    }

    const getChannelLabel = (channel: string) => {
        const option = CHANNEL_OPTIONS.find((o) => o.value === channel);
        return option?.label ?? channel;
    };

    return (
        <div className="rounded-md border">
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead>Stufe</TableHead>
                        <TableHead>Bezeichnung</TableHead>
                        <TableHead className="text-right">Tage nach Vorstufe</TableHead>
                        <TableHead className="text-right">Gebühr</TableHead>
                        <TableHead>Kommunikation</TableHead>
                        <TableHead>Auto-Eskalation</TableHead>
                        <TableHead>Genehmigung</TableHead>
                        <TableHead className="w-[50px]"></TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {configs.length === 0 ? (
                        <TableRow>
                            <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                                Keine Stufen konfiguriert
                            </TableCell>
                        </TableRow>
                    ) : (
                        configs
                            .sort((a, b) => a.stage_number - b.stage_number)
                            .map((config) => (
                                <TableRow key={config.id}>
                                    <TableCell>
                                        <Badge variant="outline">{config.stage_number}</Badge>
                                    </TableCell>
                                    <TableCell className="font-medium">
                                        {STAGE_LABELS[config.stage_number] ?? `Stufe ${config.stage_number}`}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        {config.days_after_previous ?? config.trigger_days_after_due} Tage
                                    </TableCell>
                                    <TableCell className="text-right font-mono">
                                        {formatCurrency(config.fee_amount)}
                                    </TableCell>
                                    <TableCell>
                                        {getChannelLabel(config.communication_channel ?? 'none')}
                                    </TableCell>
                                    <TableCell>
                                        <Badge variant={config.auto_escalate ? 'default' : 'secondary'}>
                                            {config.auto_escalate ? 'Ja' : 'Nein'}
                                        </Badge>
                                    </TableCell>
                                    <TableCell>
                                        <Badge variant={config.requires_approval ? 'destructive' : 'outline'}>
                                            {config.requires_approval ? 'Erforderlich' : 'Nein'}
                                        </Badge>
                                    </TableCell>
                                    <TableCell>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            onClick={() => onEdit(config)}
                                        >
                                            <Edit className="h-4 w-4" />
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))
                    )}
                </TableBody>
            </Table>
        </div>
    );
}

// ==================== Main Component ====================

export function MahnwesenSettings() {
    const { toast } = useToast();
    const { data: stageConfigs, isLoading, refetch } = useDunningStageConfigs();
    const updateConfig = useUpdateDunningStageConfig();

    const [editingConfig, setEditingConfig] = useState<DunningStageConfig | null>(null);
    const [isSaving, setIsSaving] = useState(false);

    const handleSaveConfig = async () => {
        if (!editingConfig) return;

        setIsSaving(true);
        try {
            await updateConfig.mutateAsync({
                configId: editingConfig.id,
                data: {
                    days_after_previous: editingConfig.days_after_previous,
                    fee_amount: editingConfig.fee_amount,
                    communication_channel: editingConfig.communication_channel,
                    auto_escalate: editingConfig.auto_escalate,
                    requires_approval: editingConfig.requires_approval,
                },
            });
            toast({ title: 'Konfiguration gespeichert' });
            setEditingConfig(null);
            refetch();
        } catch {
            toast({ title: 'Fehler beim Speichern', variant: 'destructive' });
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <div className="space-y-6">
            {/* Basiszins Info */}
            <BasiszinsInfoCard />

            {/* Stage Configuration */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Settings className="h-5 w-5" />
                        Mahnstufen-Konfiguration
                    </CardTitle>
                    <CardDescription>
                        Definieren Sie die Eskalationsstufen, Wartezeiten und Gebühren.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <StageConfigTable
                        configs={stageConfigs?.stages ?? []}
                        isLoading={isLoading}
                        onEdit={setEditingConfig}
                    />
                </CardContent>
            </Card>

            {/* B2B Settings */}
            <B2BSettingsCard />

            {/* Automation Settings */}
            <AutomationSettingsCard />

            {/* Edit Dialog */}
            <Dialog open={!!editingConfig} onOpenChange={(open) => !open && setEditingConfig(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            Mahnstufe {editingConfig?.stage_number} bearbeiten
                        </DialogTitle>
                        <DialogDescription>
                            {STAGE_LABELS[editingConfig?.stage_number ?? 0]}
                        </DialogDescription>
                    </DialogHeader>

                    {editingConfig && (
                        <div className="space-y-4 py-4">
                            <div className="grid gap-4 grid-cols-2">
                                <div className="space-y-2">
                                    <Label>Tage nach Vorstufe</Label>
                                    <Input
                                        type="number"
                                        value={editingConfig.days_after_previous ?? editingConfig.trigger_days_after_due}
                                        onChange={(e) =>
                                            setEditingConfig({
                                                ...editingConfig,
                                                days_after_previous: Number(e.target.value),
                                            })
                                        }
                                        min={0}
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Mahngebühr (€)</Label>
                                    <Input
                                        type="number"
                                        step="0.01"
                                        value={editingConfig.fee_amount}
                                        onChange={(e) =>
                                            setEditingConfig({
                                                ...editingConfig,
                                                fee_amount: Number(e.target.value),
                                            })
                                        }
                                        min={0}
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <Label>Kommunikationskanal</Label>
                                <Select
                                    value={editingConfig.communication_channel}
                                    onValueChange={(value) =>
                                        setEditingConfig({
                                            ...editingConfig,
                                            communication_channel: value as DunningStageConfig['communication_channel'],
                                        })
                                    }
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {CHANNEL_OPTIONS.map((option) => (
                                            <SelectItem key={option.value} value={option.value}>
                                                <div className="flex items-center gap-2">
                                                    {option.icon}
                                                    {option.label}
                                                </div>
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="flex items-center justify-between">
                                <Label>Automatische Eskalation</Label>
                                <Switch
                                    checked={editingConfig.auto_escalate}
                                    onCheckedChange={(checked: boolean) =>
                                        setEditingConfig({
                                            ...editingConfig,
                                            auto_escalate: checked,
                                        })
                                    }
                                />
                            </div>

                            <div className="flex items-center justify-between">
                                <Label>Genehmigung erforderlich</Label>
                                <Switch
                                    checked={editingConfig.requires_approval}
                                    onCheckedChange={(checked: boolean) =>
                                        setEditingConfig({
                                            ...editingConfig,
                                            requires_approval: checked,
                                        })
                                    }
                                />
                            </div>
                        </div>
                    )}

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setEditingConfig(null)}>
                            Abbrechen
                        </Button>
                        <Button onClick={handleSaveConfig} disabled={isSaving}>
                            {isSaving ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <Save className="h-4 w-4 mr-2" />
                            )}
                            Speichern
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
