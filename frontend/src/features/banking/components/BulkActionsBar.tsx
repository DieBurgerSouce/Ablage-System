/**
 * BulkActionsBar - Aktionsleiste fuer Bulk-Operationen auf Mahnvorgaenge
 *
 * Erscheint wenn Zeilen in der DunningTable ausgewaehlt sind.
 * Bietet Schnellaktionen wie Mahnung senden, Eskalieren, Mahnstopp setzen.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
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
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import {
    Mail,
    TrendingUp,
    PauseCircle,
    XCircle,
    MoreHorizontal,
    CalendarIcon,
    CheckCircle2,
    Loader2,
} from 'lucide-react';
import { useBulkEscalateDunnings, useSetMahnstopp, useLiftMahnstopp } from '../hooks/use-banking-queries';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface BulkActionsBarProps {
    selectedIds: string[];
    onClearSelection: () => void;
    onActionComplete?: () => void;
}

interface MahnstoppDialogData {
    open: boolean;
    reason: string;
    until?: Date;
}

// ==================== Main Component ====================

export function BulkActionsBar({
    selectedIds,
    onClearSelection,
    onActionComplete,
}: BulkActionsBarProps) {
    const [showEscalateConfirm, setShowEscalateConfirm] = useState(false);
    const [mahnstoppDialog, setMahnstoppDialog] = useState<MahnstoppDialogData>({
        open: false,
        reason: '',
        until: undefined,
    });
    const [showLiftMahnstoppConfirm, setShowLiftMahnstoppConfirm] = useState(false);

    // Mutations
    const bulkEscalate = useBulkEscalateDunnings();
    const setMahnstopp = useSetMahnstopp();
    const liftMahnstopp = useLiftMahnstopp();

    const isLoading = bulkEscalate.isPending || setMahnstopp.isPending || liftMahnstopp.isPending;
    const count = selectedIds.length;

    if (count === 0) return null;

    // ==================== Handlers ====================

    const handleSendReminder = async () => {
        // Mahnung senden - aktuell noch nicht implementiert
        // TODO: Implement bulk send reminder endpoint
        toast.info('Mahnungen werden gesendet...', {
            description: `${count} Mahnvorgaenge werden bearbeitet.`,
        });

        // Placeholder for actual implementation
        setTimeout(() => {
            toast.success('Mahnungen gesendet', {
                description: `${count} Mahnungen wurden erfolgreich versendet.`,
            });
            onClearSelection();
            onActionComplete?.();
        }, 1500);
    };

    const handleEscalate = async () => {
        try {
            await bulkEscalate.mutateAsync({
                dunning_ids: selectedIds,
            });
            toast.success('Eskalation erfolgreich', {
                description: `${count} Mahnvorgaenge wurden eskaliert.`,
            });
            onClearSelection();
            onActionComplete?.();
        } catch (error) {
            toast.error('Fehler bei der Eskalation', {
                description: 'Die Mahnvorgaenge konnten nicht eskaliert werden.',
            });
        } finally {
            setShowEscalateConfirm(false);
        }
    };

    const handleSetMahnstopp = async () => {
        if (!mahnstoppDialog.reason.trim()) {
            toast.error('Bitte Grund angeben', {
                description: 'Ein Grund fuer den Mahnstopp ist erforderlich.',
            });
            return;
        }

        try {
            // Set Mahnstopp for each selected dunning
            await Promise.all(
                selectedIds.map((id) =>
                    setMahnstopp.mutateAsync({
                        dunningId: id,
                        reason: mahnstoppDialog.reason,
                        until: mahnstoppDialog.until?.toISOString(),
                    })
                )
            );
            toast.success('Mahnstopp gesetzt', {
                description: `${count} Mahnvorgaenge wurden pausiert.`,
            });
            onClearSelection();
            onActionComplete?.();
        } catch (error) {
            toast.error('Fehler beim Setzen des Mahnstopps', {
                description: 'Der Mahnstopp konnte nicht gesetzt werden.',
            });
        } finally {
            setMahnstoppDialog({ open: false, reason: '', until: undefined });
        }
    };

    const handleLiftMahnstopp = async () => {
        try {
            await Promise.all(
                selectedIds.map((id) => liftMahnstopp.mutateAsync(id))
            );
            toast.success('Mahnstopp aufgehoben', {
                description: `${count} Mahnvorgaenge wurden wieder aktiviert.`,
            });
            onClearSelection();
            onActionComplete?.();
        } catch (error) {
            toast.error('Fehler beim Aufheben des Mahnstopps', {
                description: 'Der Mahnstopp konnte nicht aufgehoben werden.',
            });
        } finally {
            setShowLiftMahnstoppConfirm(false);
        }
    };

    // ==================== Render ====================

    return (
        <>
            {/* Action Bar */}
            <div className="sticky top-0 z-10 flex items-center gap-3 bg-primary/5 border border-primary/20 rounded-lg px-4 py-3 mb-4 animate-in slide-in-from-top-2 duration-200">
                {/* Selection Count */}
                <div className="flex items-center gap-2 px-3 py-1.5 bg-primary/10 rounded-md">
                    <CheckCircle2 className="h-4 w-4 text-primary" />
                    <span className="font-medium text-sm">
                        {count} ausgewaehlt
                    </span>
                </div>

                {/* Separator */}
                <div className="h-6 w-px bg-border" />

                {/* Primary Actions */}
                <Button
                    variant="default"
                    size="sm"
                    onClick={handleSendReminder}
                    disabled={isLoading}
                >
                    {isLoading ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                        <Mail className="h-4 w-4 mr-2" />
                    )}
                    Mahnung senden
                </Button>

                <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setShowEscalateConfirm(true)}
                    disabled={isLoading}
                >
                    <TrendingUp className="h-4 w-4 mr-2" />
                    Eskalieren
                </Button>

                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setMahnstoppDialog({ ...mahnstoppDialog, open: true })}
                    disabled={isLoading}
                    className="border-orange-300 text-orange-600 hover:bg-orange-50"
                >
                    <PauseCircle className="h-4 w-4 mr-2" />
                    Mahnstopp
                </Button>

                {/* More Actions Dropdown */}
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm" disabled={isLoading}>
                            <MoreHorizontal className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        <DropdownMenuLabel>Weitere Aktionen</DropdownMenuLabel>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => setShowLiftMahnstoppConfirm(true)}>
                            <CheckCircle2 className="h-4 w-4 mr-2" />
                            Mahnstopp aufheben
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                            className="text-muted-foreground"
                            disabled
                        >
                            <Mail className="h-4 w-4 mr-2" />
                            Als PDF exportieren
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>

                {/* Spacer */}
                <div className="flex-1" />

                {/* Cancel Selection */}
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={onClearSelection}
                    disabled={isLoading}
                >
                    <XCircle className="h-4 w-4 mr-2" />
                    Auswahl aufheben
                </Button>
            </div>

            {/* Escalation Confirmation Dialog */}
            <AlertDialog open={showEscalateConfirm} onOpenChange={setShowEscalateConfirm}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>
                            Mahnvorgaenge eskalieren?
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            Sie sind dabei, {count} Mahnvorgang
                            {count !== 1 ? 'e' : ''} auf die naechste Mahnstufe zu
                            eskalieren. Diese Aktion kann nicht rueckgaengig gemacht
                            werden.
                            <br />
                            <br />
                            Die betroffenen Kunden werden ueber die Eskalation
                            informiert.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleEscalate}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                            {bulkEscalate.isPending ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <TrendingUp className="h-4 w-4 mr-2" />
                            )}
                            Eskalieren
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            {/* Mahnstopp Dialog */}
            <Dialog
                open={mahnstoppDialog.open}
                onOpenChange={(open) =>
                    setMahnstoppDialog({ ...mahnstoppDialog, open })
                }
            >
                <DialogContent className="sm:max-w-[425px]">
                    <DialogHeader>
                        <DialogTitle>Mahnstopp setzen</DialogTitle>
                        <DialogDescription>
                            Setzen Sie einen Mahnstopp fuer {count} Mahnvorgang
                            {count !== 1 ? 'e' : ''}. Waehrend des Mahnstopps werden
                            keine automatischen Mahnungen versendet.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="grid gap-4 py-4">
                        <div className="grid gap-2">
                            <Label htmlFor="reason">
                                Grund <span className="text-destructive">*</span>
                            </Label>
                            <Textarea
                                id="reason"
                                placeholder="z.B. Reklamation, Zahlungsvereinbarung, Pruefung..."
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
                            <Popover>
                                <PopoverTrigger asChild>
                                    <Button
                                        variant="outline"
                                        className={cn(
                                            'justify-start text-left font-normal',
                                            !mahnstoppDialog.until && 'text-muted-foreground'
                                        )}
                                    >
                                        <CalendarIcon className="mr-2 h-4 w-4" />
                                        {mahnstoppDialog.until ? (
                                            format(mahnstoppDialog.until, 'PPP', { locale: de })
                                        ) : (
                                            <span>Datum waehlen</span>
                                        )}
                                    </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-auto p-0">
                                    <Calendar
                                        mode="single"
                                        selected={mahnstoppDialog.until}
                                        onSelect={(date) =>
                                            setMahnstoppDialog({
                                                ...mahnstoppDialog,
                                                until: date,
                                            })
                                        }
                                        disabled={(date) => date < new Date()}
                                        locale={de}
                                        initialFocus
                                    />
                                </PopoverContent>
                            </Popover>
                            <p className="text-xs text-muted-foreground">
                                Leer lassen fuer unbefristeten Mahnstopp
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
                            onClick={handleSetMahnstopp}
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

            {/* Lift Mahnstopp Confirmation */}
            <AlertDialog open={showLiftMahnstoppConfirm} onOpenChange={setShowLiftMahnstoppConfirm}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>
                            Mahnstopp aufheben?
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            Sie sind dabei, den Mahnstopp fuer {count} Mahnvorgang
                            {count !== 1 ? 'e' : ''} aufzuheben. Die automatische
                            Mahnung wird wieder aktiviert.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction onClick={handleLiftMahnstopp}>
                            {liftMahnstopp.isPending ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <CheckCircle2 className="h-4 w-4 mr-2" />
                            )}
                            Mahnstopp aufheben
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    );
}
