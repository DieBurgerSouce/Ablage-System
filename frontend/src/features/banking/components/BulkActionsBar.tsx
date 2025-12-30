/**
 * BulkActionsBar - Aktionsleiste für Bulk-Operationen auf Mahnvorgänge
 *
 * Erscheint wenn Zeilen in der DunningTable ausgewählt sind.
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
import { useToast } from '@/components/ui/use-toast';
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
import { useBulkEscalateDunnings, useBulkSendReminders, useSetMahnstopp, useLiftMahnstopp } from '../hooks/use-banking-queries';

// ==================== Types ====================

interface BulkActionsBarProps {
    selectedIds: string[];
    onClearSelection: () => void;
    onActionComplete?: () => void;
}

interface MahnstoppDialogData {
    open: boolean;
    reason: string;
    until?: string;  // ISO date string statt Date
}

// ==================== Main Component ====================

export function BulkActionsBar({
    selectedIds,
    onClearSelection,
    onActionComplete,
}: BulkActionsBarProps) {
    const { toast } = useToast();
    const [showEscalateConfirm, setShowEscalateConfirm] = useState(false);
    const [mahnstoppDialog, setMahnstoppDialog] = useState<MahnstoppDialogData>({
        open: false,
        reason: '',
        until: undefined,
    });
    const [showLiftMahnstoppConfirm, setShowLiftMahnstoppConfirm] = useState(false);

    // Mutations
    const bulkEscalate = useBulkEscalateDunnings();
    const bulkSendReminders = useBulkSendReminders();
    const setMahnstopp = useSetMahnstopp();
    const liftMahnstopp = useLiftMahnstopp();

    const isLoading = bulkEscalate.isPending || bulkSendReminders.isPending || setMahnstopp.isPending || liftMahnstopp.isPending;
    const count = selectedIds.length;

    if (count === 0) return null;

    // ==================== Handlers ====================

    const handleSendReminder = async () => {
        try {
            const result = await bulkSendReminders.mutateAsync({
                dunningIds: selectedIds,
                channel: 'email',
            });

            if (result.failed > 0) {
                toast({
                    title: 'Mahnungen teilweise versendet',
                    description: `${result.sent} von ${result.total} Mahnungen wurden versendet. ${result.failed} fehlgeschlagen.`,
                });
            } else {
                toast({
                    title: 'Mahnungen versendet',
                    description: `${result.sent} Mahnungen wurden erfolgreich versendet.`,
                });
            }
            onClearSelection();
            onActionComplete?.();
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler';
            toast({
                variant: 'destructive',
                title: 'Fehler beim Versenden der Mahnungen',
                description: errorMessage,
            });
        }
    };

    const handleEscalate = async () => {
        try {
            await bulkEscalate.mutateAsync({
                dunningIds: selectedIds,
            });
            toast({
                title: 'Eskalation erfolgreich',
                description: `${count} Mahnvorgänge wurden eskaliert.`,
            });
            onClearSelection();
            onActionComplete?.();
        } catch {
            toast({
                variant: 'destructive',
                title: 'Fehler bei der Eskalation',
                description: 'Die Mahnvorgänge konnten nicht eskaliert werden.',
            });
        } finally {
            setShowEscalateConfirm(false);
        }
    };

    const handleSetMahnstopp = async () => {
        if (!mahnstoppDialog.reason.trim()) {
            toast({
                variant: 'destructive',
                title: 'Bitte Grund angeben',
                description: 'Ein Grund für den Mahnstopp ist erforderlich.',
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
                        until: mahnstoppDialog.until,
                    })
                )
            );
            toast({
                title: 'Mahnstopp gesetzt',
                description: `${count} Mahnvorgänge wurden pausiert.`,
            });
            onClearSelection();
            onActionComplete?.();
        } catch {
            toast({
                variant: 'destructive',
                title: 'Fehler beim Setzen des Mahnstopps',
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
            toast({
                title: 'Mahnstopp aufgehoben',
                description: `${count} Mahnvorgänge wurden wieder aktiviert.`,
            });
            onClearSelection();
            onActionComplete?.();
        } catch {
            toast({
                variant: 'destructive',
                title: 'Fehler beim Aufheben des Mahnstopps',
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
                        {count} ausgewählt
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
                            Mahnvorgänge eskalieren?
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            Sie sind dabei, {count} {count !== 1 ? 'Mahnvorgänge' : 'Mahnvorgang'} auf die nächste Mahnstufe zu
                            eskalieren. Diese Aktion kann nicht rückgängig gemacht
                            werden.
                            <br />
                            <br />
                            Die betroffenen Kunden werden über die Eskalation
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
                            Setzen Sie einen Mahnstopp für {count} {count !== 1 ? 'Mahnvorgänge' : 'Mahnvorgang'}. Während des Mahnstopps werden
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
                            Sie sind dabei, den Mahnstopp für {count} {count !== 1 ? 'Mahnvorgänge' : 'Mahnvorgang'} aufzuheben. Die automatische
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
