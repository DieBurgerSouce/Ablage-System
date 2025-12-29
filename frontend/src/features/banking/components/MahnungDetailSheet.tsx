/**
 * MahnungDetailSheet - Detailansicht für einen Mahnvorgang
 *
 * Slideout-Panel mit:
 * - Vollständige Rechnungsdetails
 * - Mahnung-Timeline (aus History)
 * - Telefon-Protokoll
 * - Notizen hinzufügen
 * - Aktionen (Eskalieren, Mahnstopp, B2B Pauschale, etc.)
 */

import { useState } from 'react';
import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
    SheetDescription,
} from '@/components/ui/sheet';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/components/ui/use-toast';
import {
    Building2,
    User,
    PauseCircle,
    PlayCircle,
    TrendingUp,
    Phone,
    Mail,
    FileText,
    Euro,
    Calendar as CalendarIcon,
    Clock,
    History,
    AlertTriangle,
    CheckCircle2,
    Loader2,
    Copy,
} from 'lucide-react';

// Date formatting helper (replaces date-fns)
function formatDateWithTime(dateStr: string, pattern: 'datetime' | 'date' = 'datetime'): string {
    const date = new Date(dateStr);
    if (pattern === 'date') {
        return date.toLocaleDateString('de-DE');
    }
    return date.toLocaleDateString('de-DE') + ' ' + date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}
import type { DunningRecord, PhoneCallLog, MahnungHistoryEntry, MahnungHistory } from '@/types/models/banking';
import {
    useDunningHistory,
    usePhoneCalls,
    useSetMahnstopp,
    useLiftMahnstopp,
    useClaimB2BPauschale,
    useVerzugszinsen,
} from '../hooks/use-banking-queries';
import { formatCurrency, formatDate } from '../utils/format';
import { cn } from '@/lib/utils';
import { CustomerDunningOverrideForm } from './CustomerDunningOverrideForm';

// ==================== Types ====================

interface MahnungDetailSheetProps {
    dunning: DunningRecord | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onLogPhoneCall?: () => void;
    onEscalate?: () => void;
}

interface MahnstoppDialogState {
    open: boolean;
    reason: string;
    until?: string;
}

// ==================== Helper Components ====================

function InfoRow({ label, value, icon }: { label: string; value: React.ReactNode; icon?: React.ReactNode }) {
    return (
        <div className="flex items-start gap-3 py-2">
            {icon && <div className="text-muted-foreground mt-0.5">{icon}</div>}
            <div className="flex-1 min-w-0">
                <div className="text-sm text-muted-foreground">{label}</div>
                <div className="font-medium">{value || '-'}</div>
            </div>
        </div>
    );
}

function HistoryItem({ entry }: { entry: MahnungHistory }) {
    const getActionIcon = (actionType: string) => {
        switch (actionType) {
            case 'reminder_sent':
                return <Mail className="h-4 w-4 text-blue-500" />;
            case 'escalated':
                return <TrendingUp className="h-4 w-4 text-orange-500" />;
            case 'phone_call':
                return <Phone className="h-4 w-4 text-green-500" />;
            case 'payment_received':
                return <CheckCircle2 className="h-4 w-4 text-green-600" />;
            case 'mahnstopp_set':
                return <PauseCircle className="h-4 w-4 text-orange-500" />;
            case 'mahnstopp_lifted':
                return <PlayCircle className="h-4 w-4 text-green-500" />;
            default:
                return <History className="h-4 w-4 text-muted-foreground" />;
        }
    };

    const getActionLabel = (actionType: string) => {
        const labels: Record<string, string> = {
            'reminder_sent': 'Erinnerung gesendet',
            'escalated': 'Eskaliert',
            'phone_call': 'Telefonanruf',
            'payment_received': 'Zahlung eingegangen',
            'mahnstopp_set': 'Mahnstopp gesetzt',
            'mahnstopp_lifted': 'Mahnstopp aufgehoben',
            'document_generated': 'Dokument erstellt',
            'b2b_pauschale_claimed': '40€ Pauschale beansprucht',
        };
        return labels[actionType] || actionType;
    };

    return (
        <div className="flex gap-3 py-3 border-b last:border-0">
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-muted flex items-center justify-center">
                {getActionIcon(entry.action_type)}
            </div>
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="font-medium">{getActionLabel(entry.action_type)}</span>
                    <Badge variant="outline" className="text-xs">
                        Stufe {entry.mahn_stufe}
                    </Badge>
                </div>
                {entry.notes && (
                    <p className="text-sm text-muted-foreground mt-1">{entry.notes}</p>
                )}
                <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatDateWithTime(entry.action_timestamp)}
                    </span>
                    {entry.outcome && (
                        <Badge variant={entry.outcome === 'success' ? 'default' : 'secondary'} className="text-xs">
                            {entry.outcome === 'success' ? 'Erfolgreich' : entry.outcome}
                        </Badge>
                    )}
                </div>
            </div>
        </div>
    );
}

function PhoneCallItem({ call }: { call: PhoneCallLog }) {
    const getOutcomeColor = (outcome: string) => {
        switch (outcome) {
            case 'reached':
            case 'payment_promised':
                return 'text-green-600 bg-green-50';
            case 'not_reached':
            case 'voicemail':
                return 'text-orange-600 bg-orange-50';
            case 'dispute_raised':
                return 'text-red-600 bg-red-50';
            default:
                return 'text-muted-foreground bg-muted';
        }
    };

    const getOutcomeLabel = (outcome: string) => {
        const labels: Record<string, string> = {
            'reached': 'Erreicht',
            'not_reached': 'Nicht erreicht',
            'voicemail': 'Mailbox',
            'callback_requested': 'Rückruf erbeten',
            'payment_promised': 'Zahlung zugesagt',
            'dispute_raised': 'Reklamation',
        };
        return labels[outcome] || outcome;
    };

    return (
        <Card className="mb-3">
            <CardContent className="p-4">
                <div className="flex items-start justify-between">
                    <div>
                        <div className="font-medium">{call.contact_name}</div>
                        {call.phone_number && (
                            <div className="text-sm text-muted-foreground flex items-center gap-1">
                                <Phone className="h-3 w-3" />
                                {call.phone_number}
                            </div>
                        )}
                    </div>
                    <Badge className={cn('text-xs', getOutcomeColor(call.outcome))}>
                        {getOutcomeLabel(call.outcome)}
                    </Badge>
                </div>
                {call.notes && (
                    <p className="text-sm mt-2 bg-muted/50 p-2 rounded">{call.notes}</p>
                )}
                <div className="flex items-center justify-between mt-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                        <CalendarIcon className="h-3 w-3" />
                        {formatDate(call.called_at)}
                    </span>
                    {call.follow_up_required && call.follow_up_date && (
                        <span className="flex items-center gap-1 text-orange-600">
                            <AlertTriangle className="h-3 w-3" />
                            Follow-up: {formatDateWithTime(call.follow_up_date, 'date')}
                        </span>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

function VerzugszinsenCard({ dunningId }: { dunningId: string }) {
    const { data, isLoading, isError, error } = useVerzugszinsen(dunningId);

    if (isLoading) {
        return <Skeleton className="h-24" />;
    }

    if (isError) {
        return (
            <Card className="border-red-200 bg-red-50/50">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2 text-red-600">
                        <AlertTriangle className="h-4 w-4" />
                        Fehler beim Laden der Verzugszinsen
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-sm text-muted-foreground">
                        {error instanceof Error ? error.message : 'Die Verzugszinsen konnten nicht berechnet werden.'}
                    </p>
                </CardContent>
            </Card>
        );
    }

    if (!data) return null;

    return (
        <Card className="border-green-200 bg-green-50/50">
            <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                    <Euro className="h-4 w-4" />
                    Verzugszinsen nach BGB §288
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Basiszins:</span>
                    <span>{data.base_rate_percent ?? 0}%</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">
                        Aufschlag ({data.is_b2b ? 'B2B +9%' : 'B2C +5%'}):
                    </span>
                    <span>{data.zusatz_rate_percent ?? 0}%</span>
                </div>
                <Separator />
                <div className="flex justify-between font-medium">
                    <span>Gesamtzins p.a.:</span>
                    <span>{data.total_rate_percent ?? data.interest_rate}%</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">
                        Verzugstage ({data.days_overdue}):
                    </span>
                    <span className="font-mono">{formatCurrency(data.interest_amount)}</span>
                </div>
            </CardContent>
        </Card>
    );
}

// ==================== Main Component ====================

export function MahnungDetailSheet({
    dunning,
    open,
    onOpenChange,
    onLogPhoneCall,
    onEscalate,
}: MahnungDetailSheetProps) {
    const { toast } = useToast();
    const [activeTab, setActiveTab] = useState('details');
    const [mahnstoppDialog, setMahnstoppDialog] = useState<MahnstoppDialogState>({
        open: false,
        reason: '',
        until: undefined,
    });
    const [customerSettingsOpen, setCustomerSettingsOpen] = useState(false);

    // Queries
    const historyQuery = useDunningHistory(dunning?.id || '');
    const phoneCallsQuery = usePhoneCalls(dunning?.id || '');

    // Mutations
    const setMahnstopp = useSetMahnstopp();
    const liftMahnstopp = useLiftMahnstopp();
    const claimPauschale = useClaimB2BPauschale();

    const isLoading = setMahnstopp.isPending || liftMahnstopp.isPending || claimPauschale.isPending;

    if (!dunning) return null;

    // ==================== Handlers ====================

    const handleToggleMahnstopp = async () => {
        if (dunning.mahnstopp) {
            // Mahnstopp aufheben - direkt ausführen
            try {
                await liftMahnstopp.mutateAsync(dunning.id);
                toast({
                    title: 'Mahnstopp aufgehoben',
                    description: 'Die automatische Mahnung ist wieder aktiviert.',
                });
            } catch (error) {
                const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler';
                toast({
                    title: 'Mahnstopp konnte nicht aufgehoben werden',
                    description: errorMessage,
                    variant: 'destructive',
                });
            }
        } else {
            // Mahnstopp setzen - Dialog öffnen
            setMahnstoppDialog({ open: true, reason: '', until: undefined });
        }
    };

    const handleConfirmMahnstopp = async () => {
        if (!mahnstoppDialog.reason.trim()) {
            toast({
                title: 'Bitte Grund angeben',
                description: 'Ein Grund für den Mahnstopp ist erforderlich.',
                variant: 'destructive',
            });
            return;
        }

        try {
            await setMahnstopp.mutateAsync({
                dunningId: dunning.id,
                reason: mahnstoppDialog.reason,
                until: mahnstoppDialog.until,
            });
            toast({
                title: 'Mahnstopp gesetzt',
                description: 'Der Mahnvorgang wurde pausiert.',
            });
            setMahnstoppDialog({ open: false, reason: '', until: undefined });
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler';
            toast({
                title: 'Mahnstopp konnte nicht gesetzt werden',
                description: errorMessage,
                variant: 'destructive',
            });
        }
    };

    const handleClaimPauschale = async () => {
        try {
            await claimPauschale.mutateAsync(dunning.id);
            toast({
                title: '40€ Pauschale beansprucht',
                description: 'Pauschale nach §288 Abs. 5 BGB wird zur Forderung hinzugefügt.',
            });
        } catch {
            toast({
                title: 'Pauschale konnte nicht beansprucht werden',
                variant: 'destructive',
            });
        }
    };

    const handleCopyInvoiceNumber = () => {
        navigator.clipboard.writeText(dunning.invoice_number || '');
        toast({ title: 'Rechnungsnummer kopiert' });
    };

    // ==================== Render ====================

    const daysOverdue = dunning.due_date
        ? Math.max(0, Math.floor((Date.now() - new Date(dunning.due_date).getTime()) / (1000 * 60 * 60 * 24)))
        : 0;

    return (
        <>
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent className="w-full sm:max-w-xl overflow-hidden flex flex-col">
                <SheetHeader className="space-y-1">
                    <div className="flex items-center gap-2">
                        <SheetTitle className="flex items-center gap-2">
                            <FileText className="h-5 w-5" />
                            {dunning.invoice_number || 'Ohne Rechnungsnr.'}
                        </SheetTitle>
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-6 w-6"
                                        onClick={handleCopyInvoiceNumber}
                                    >
                                        <Copy className="h-3 w-3" />
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent>Rechnungsnummer kopieren</TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    </div>
                    <SheetDescription className="flex items-center gap-2 flex-wrap">
                        <Badge variant={dunning.is_b2b ? 'default' : 'secondary'}>
                            {dunning.is_b2b ? (
                                <>
                                    <Building2 className="h-3 w-3 mr-1" />
                                    B2B
                                </>
                            ) : (
                                <>
                                    <User className="h-3 w-3 mr-1" />
                                    B2C
                                </>
                            )}
                        </Badge>
                        {dunning.mahnstopp && (
                            <Badge variant="outline" className="border-orange-500 text-orange-600">
                                <PauseCircle className="h-3 w-3 mr-1" />
                                Mahnstopp
                            </Badge>
                        )}
                        {daysOverdue > 0 && (
                            <Badge variant="destructive">
                                +{daysOverdue} Tage überfällig
                            </Badge>
                        )}
                    </SheetDescription>
                </SheetHeader>

                <Separator className="my-4" />

                {/* Quick Actions */}
                <div className="flex flex-wrap gap-2 mb-4">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleToggleMahnstopp}
                        disabled={isLoading}
                        className={cn(
                            dunning.mahnstopp && 'border-green-500 text-green-600 hover:bg-green-50'
                        )}
                    >
                        {isLoading ? (
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : dunning.mahnstopp ? (
                            <PlayCircle className="h-4 w-4 mr-2" />
                        ) : (
                            <PauseCircle className="h-4 w-4 mr-2" />
                        )}
                        {dunning.mahnstopp ? 'Mahnstopp aufheben' : 'Mahnstopp'}
                    </Button>

                    <Button
                        variant="outline"
                        size="sm"
                        onClick={onLogPhoneCall}
                    >
                        <Phone className="h-4 w-4 mr-2" />
                        Anruf protokollieren
                    </Button>

                    <Button
                        variant="secondary"
                        size="sm"
                        onClick={onEscalate}
                    >
                        <TrendingUp className="h-4 w-4 mr-2" />
                        Eskalieren
                    </Button>

                    {dunning.is_b2b && !dunning.b2b_pauschale_claimed && (
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={handleClaimPauschale}
                                        disabled={isLoading}
                                        className="border-green-500 text-green-600 hover:bg-green-50"
                                    >
                                        <Euro className="h-4 w-4 mr-2" />
                                        +40€ Pauschale
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent>
                                    Pauschale nach §288 Abs. 5 BGB (nur B2B)
                                </TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    )}

                    {dunning.business_entity_id && (
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => setCustomerSettingsOpen(true)}
                                    >
                                        <Building2 className="h-4 w-4 mr-2" />
                                        Kundeneinstellungen
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent>
                                    Individuelle Mahneinstellungen für diesen Kunden
                                </TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    )}
                </div>

                {/* Tabs */}
                <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
                    <TabsList className="grid w-full grid-cols-3">
                        <TabsTrigger value="details">Details</TabsTrigger>
                        <TabsTrigger value="history">
                            Verlauf
                            {historyQuery.data?.items && historyQuery.data.items.length > 0 && (
                                <Badge variant="secondary" className="ml-1.5 h-5 w-5 p-0 text-xs">
                                    {historyQuery.data.items.length}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger value="calls">
                            Anrufe
                            {phoneCallsQuery.data?.items && phoneCallsQuery.data.items.length > 0 && (
                                <Badge variant="secondary" className="ml-1.5 h-5 w-5 p-0 text-xs">
                                    {phoneCallsQuery.data.items.length}
                                </Badge>
                            )}
                        </TabsTrigger>
                    </TabsList>

                    <ScrollArea className="flex-1 mt-4">
                        {/* Details Tab */}
                        <TabsContent value="details" className="mt-0 space-y-6">
                            {/* Debtor Info */}
                            <Card>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm">Debitor</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-2">
                                    <InfoRow
                                        label="Name"
                                        value={dunning.debtor_name}
                                        icon={<User className="h-4 w-4" />}
                                    />
                                    <InfoRow
                                        label="E-Mail"
                                        value={dunning.debtor_email || '-'}
                                    />
                                    <InfoRow
                                        label="Kundentyp"
                                        value={
                                            <Badge variant={dunning.is_b2b ? 'default' : 'outline'}>
                                                {dunning.is_b2b ? 'Geschaeftskunde (B2B)' : 'Privatkunde (B2C)'}
                                            </Badge>
                                        }
                                    />
                                </CardContent>
                            </Card>

                            {/* Invoice Info */}
                            <Card>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm">Rechnung</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-2">
                                    <InfoRow
                                        label="Rechnungsnummer"
                                        value={dunning.invoice_number}
                                        icon={<FileText className="h-4 w-4" />}
                                    />
                                    <InfoRow
                                        label="Rechnungsdatum"
                                        value={dunning.invoice_date ? formatDate(dunning.invoice_date) : '-'}
                                        icon={<CalendarIcon className="h-4 w-4" />}
                                    />
                                    <InfoRow
                                        label="Fälligkeit"
                                        value={
                                            <div className="flex items-center gap-2">
                                                <span>{dunning.due_date ? formatDate(dunning.due_date) : '-'}</span>
                                                {daysOverdue > 0 && (
                                                    <Badge variant="destructive" className="text-xs">
                                                        +{daysOverdue} Tage
                                                    </Badge>
                                                )}
                                            </div>
                                        }
                                        icon={<Clock className="h-4 w-4" />}
                                    />
                                </CardContent>
                            </Card>

                            {/* Amount Info */}
                            <Card>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm">Beträge</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-2">
                                    <InfoRow
                                        label="Offener Betrag"
                                        value={
                                            <span className="font-mono text-lg">
                                                {formatCurrency(dunning.outstanding_amount ?? 0)}
                                            </span>
                                        }
                                        icon={<Euro className="h-4 w-4" />}
                                    />
                                    <InfoRow
                                        label="Mahngebühren"
                                        value={formatCurrency(dunning.reminder_fee)}
                                    />
                                    <InfoRow
                                        label="Verzugszinsen"
                                        value={formatCurrency(dunning.accrued_interest)}
                                    />
                                    {dunning.b2b_pauschale_claimed && (
                                        <InfoRow
                                            label="B2B Pauschale"
                                            value={
                                                <span className="text-green-600 font-medium">
                                                    +40,00 € (§288 Abs. 5 BGB)
                                                </span>
                                            }
                                        />
                                    )}
                                    <Separator />
                                    <InfoRow
                                        label="Gesamtforderung"
                                        value={
                                            <span className="font-mono text-lg font-bold text-primary">
                                                {formatCurrency(dunning.total_outstanding ?? dunning.outstanding_amount ?? 0)}
                                            </span>
                                        }
                                    />
                                </CardContent>
                            </Card>

                            {/* Verzugszinsen Card */}
                            <VerzugszinsenCard dunningId={dunning.id} />

                            {/* Mahnstopp Info */}
                            {dunning.mahnstopp && (
                                <Card className="border-orange-200 bg-orange-50/50">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-sm flex items-center gap-2 text-orange-600">
                                            <PauseCircle className="h-4 w-4" />
                                            Mahnstopp aktiv
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent className="space-y-2">
                                        <InfoRow
                                            label="Grund"
                                            value={dunning.mahnstopp_reason || 'Kein Grund angegeben'}
                                        />
                                        {dunning.mahnstopp_until && (
                                            <InfoRow
                                                label="Bis"
                                                value={formatDate(dunning.mahnstopp_until)}
                                            />
                                        )}
                                    </CardContent>
                                </Card>
                            )}
                        </TabsContent>

                        {/* History Tab */}
                        <TabsContent value="history" className="mt-0">
                            {historyQuery.isLoading ? (
                                <div className="space-y-3">
                                    {[1, 2, 3].map((i) => (
                                        <Skeleton key={i} className="h-20" />
                                    ))}
                                </div>
                            ) : historyQuery.data?.items && historyQuery.data.items.length > 0 ? (
                                <div className="space-y-0">
                                    {historyQuery.data.items.map((entry: MahnungHistoryEntry) => (
                                        <HistoryItem key={entry.id} entry={entry} />
                                    ))}
                                </div>
                            ) : (
                                <div className="text-center py-8 text-muted-foreground">
                                    <History className="h-12 w-12 mx-auto mb-3 opacity-50" />
                                    <p>Noch keine Verlaufseinträge</p>
                                </div>
                            )}
                        </TabsContent>

                        {/* Phone Calls Tab */}
                        <TabsContent value="calls" className="mt-0">
                            <Button
                                variant="outline"
                                size="sm"
                                className="w-full mb-4"
                                onClick={onLogPhoneCall}
                            >
                                <Phone className="h-4 w-4 mr-2" />
                                Neuen Anruf protokollieren
                            </Button>

                            {phoneCallsQuery.isLoading ? (
                                <div className="space-y-3">
                                    {[1, 2].map((i) => (
                                        <Skeleton key={i} className="h-24" />
                                    ))}
                                </div>
                            ) : phoneCallsQuery.data?.items && phoneCallsQuery.data.items.length > 0 ? (
                                <div>
                                    {phoneCallsQuery.data.items.map((call: PhoneCallLog) => (
                                        <PhoneCallItem key={call.id} call={call} />
                                    ))}
                                </div>
                            ) : (
                                <div className="text-center py-8 text-muted-foreground">
                                    <Phone className="h-12 w-12 mx-auto mb-3 opacity-50" />
                                    <p>Noch keine Telefonkontakte</p>
                                </div>
                            )}
                        </TabsContent>
                    </ScrollArea>
                </Tabs>
            </SheetContent>
        </Sheet>

        {/* Mahnstopp Dialog */}
        <Dialog
            open={mahnstoppDialog.open}
            onOpenChange={(open) => setMahnstoppDialog({ ...mahnstoppDialog, open })}
        >
            <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                    <DialogTitle>Mahnstopp setzen</DialogTitle>
                    <DialogDescription>
                        Setzen Sie einen Mahnstopp für diesen Mahnvorgang. Während des
                        Mahnstopps werden keine automatischen Mahnungen versendet.
                    </DialogDescription>
                </DialogHeader>

                <div className="grid gap-4 py-4">
                    <div className="grid gap-2">
                        <Label htmlFor="mahnstopp-reason">
                            Grund <span className="text-destructive">*</span>
                        </Label>
                        <Textarea
                            id="mahnstopp-reason"
                            placeholder="z.B. Reklamation, Zahlungsvereinbarung, Prüfung..."
                            value={mahnstoppDialog.reason}
                            onChange={(e) =>
                                setMahnstoppDialog({
                                    ...mahnstoppDialog,
                                    reason: e.target.value,
                                })
                            }
                            rows={3}
                        />
                    </div>

                    <div className="grid gap-2">
                        <Label>Mahnstopp bis (optional)</Label>
                        <div className="relative">
                            <CalendarIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input
                                type="date"
                                value={mahnstoppDialog.until || ''}
                                onChange={(e) =>
                                    setMahnstoppDialog({
                                        ...mahnstoppDialog,
                                        until: e.target.value || undefined,
                                    })
                                }
                                min={new Date().toISOString().split('T')[0]}
                                className="pl-10"
                            />
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Leer lassen für unbefristeten Mahnstopp
                        </p>
                    </div>
                </div>

                <DialogFooter>
                    <Button
                        variant="outline"
                        onClick={() =>
                            setMahnstoppDialog({ open: false, reason: '', until: undefined })
                        }
                    >
                        Abbrechen
                    </Button>
                    <Button
                        onClick={handleConfirmMahnstopp}
                        disabled={setMahnstopp.isPending || !mahnstoppDialog.reason.trim()}
                        className="bg-orange-600 hover:bg-orange-700"
                    >
                        {setMahnstopp.isPending ? (
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                            <PauseCircle className="h-4 w-4 mr-2" />
                        )}
                        Mahnstopp setzen
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>

        {/* Customer Dunning Settings Dialog */}
        {dunning.business_entity_id && (
            <CustomerDunningOverrideForm
                businessEntityId={dunning.business_entity_id}
                businessEntityName={dunning.debtor_name ?? undefined}
                open={customerSettingsOpen}
                onOpenChange={setCustomerSettingsOpen}
            />
        )}
    </>
    );
}
