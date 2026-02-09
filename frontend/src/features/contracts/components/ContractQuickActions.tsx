/**
 * ContractQuickActions Component
 *
 * Schnellaktionen fuer Vertraege:
 * - Als verlaengert markieren
 * - Kuendigen
 * - Archivieren
 * - Erinnerung senden
 */

import { useState } from 'react';
import {
  MoreHorizontal,
  RefreshCw,
  Archive,
  XCircle,
  Bell,
  FileEdit,
  Eye,
  Trash2,
  CheckCircle2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuLabel,
} from '@/components/ui/dropdown-menu';
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import type { Contract } from '../types/contract-types';

interface ContractQuickActionsProps {
  contract: Contract;
  onView?: (contract: Contract) => void;
  onEdit?: (contract: Contract) => void;
  onDelete?: (contract: Contract) => void;
  onRenew?: (contract: Contract) => void;
  onTerminate?: (contract: Contract, reason: string) => void;
  onArchive?: (contract: Contract) => void;
  onSendReminder?: (contract: Contract) => void;
  variant?: 'dropdown' | 'buttons';
  isLoading?: boolean;
}

type DialogType = 'terminate' | 'archive' | 'delete' | 'renew' | null;

export function ContractQuickActions({
  contract,
  onView,
  onEdit,
  onDelete,
  onRenew,
  onTerminate,
  onArchive,
  onSendReminder,
  variant = 'dropdown',
  isLoading = false,
}: ContractQuickActionsProps) {
  const [activeDialog, setActiveDialog] = useState<DialogType>(null);
  const [terminationReason, setTerminationReason] = useState('');

  const isActive = contract.status === 'active' || contract.status === 'expiring_soon';
  const canRenew = isActive && contract.auto_renewal;
  const canTerminate = isActive;
  const canArchive = contract.status === 'expired' || contract.status === 'terminated';

  const handleTerminate = () => {
    if (onTerminate && terminationReason) {
      onTerminate(contract, terminationReason);
      setActiveDialog(null);
      setTerminationReason('');
      toast.success('Vertrag wird gekuendigt');
    }
  };

  const handleRenew = () => {
    if (onRenew) {
      onRenew(contract);
      setActiveDialog(null);
      toast.success('Vertrag wird verlaengert');
    }
  };

  const handleArchive = () => {
    if (onArchive) {
      onArchive(contract);
      setActiveDialog(null);
      toast.success('Vertrag archiviert');
    }
  };

  const handleDelete = () => {
    if (onDelete) {
      onDelete(contract);
      setActiveDialog(null);
    }
  };

  const handleSendReminder = () => {
    if (onSendReminder) {
      onSendReminder(contract);
      toast.success('Erinnerung wird gesendet');
    }
  };

  if (variant === 'buttons') {
    return (
      <div className="flex items-center gap-2">
        {onView && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onView(contract)}
            disabled={isLoading}
          >
            <Eye className="h-4 w-4 mr-1" />
            Ansehen
          </Button>
        )}
        {onEdit && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onEdit(contract)}
            disabled={isLoading}
          >
            <FileEdit className="h-4 w-4 mr-1" />
            Bearbeiten
          </Button>
        )}
        {canRenew && onRenew && (
          <Button
            variant="default"
            size="sm"
            onClick={() => setActiveDialog('renew')}
            disabled={isLoading}
          >
            <RefreshCw className="h-4 w-4 mr-1" />
            Verlaengern
          </Button>
        )}
        {canTerminate && onTerminate && (
          <Button
            variant="outline"
            size="sm"
            className="text-red-600 hover:text-red-700"
            onClick={() => setActiveDialog('terminate')}
            disabled={isLoading}
          >
            <XCircle className="h-4 w-4 mr-1" />
            Kuendigen
          </Button>
        )}

        {/* Dialogs */}
        {renderDialogs()}
      </div>
    );
  }

  function renderDialogs() {
    return (
      <>
        {/* Renew Dialog */}
        <AlertDialog open={activeDialog === 'renew'} onOpenChange={(open) => !open && setActiveDialog(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Vertrag verlaengern</AlertDialogTitle>
              <AlertDialogDescription>
                Moechten Sie den Vertrag "{contract.title}" verlaengern?
                {contract.renewal_period_months && (
                  <span className="block mt-2">
                    Der Vertrag wird um {contract.renewal_period_months} Monate verlaengert.
                  </span>
                )}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Abbrechen</AlertDialogCancel>
              <AlertDialogAction onClick={handleRenew}>
                <CheckCircle2 className="h-4 w-4 mr-2" />
                Verlaengern
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Terminate Dialog */}
        <Dialog open={activeDialog === 'terminate'} onOpenChange={(open) => !open && setActiveDialog(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Vertrag kuendigen</DialogTitle>
              <DialogDescription>
                Moechten Sie den Vertrag "{contract.title}" ({contract.contract_number}) kuendigen?
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="reason">Kuendigungsgrund</Label>
                <Textarea
                  id="reason"
                  placeholder="Geben Sie den Grund fuer die Kuendigung an..."
                  value={terminationReason}
                  onChange={(e) => setTerminationReason(e.target.value)}
                  rows={3}
                />
              </div>
              {contract.notice_period_days > 0 && (
                <p className="text-sm text-muted-foreground">
                  <strong>Hinweis:</strong> Die Kuendigungsfrist betraegt {contract.notice_period_days} Tage.
                </p>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setActiveDialog(null)}>
                Abbrechen
              </Button>
              <Button
                variant="destructive"
                onClick={handleTerminate}
                disabled={!terminationReason.trim()}
              >
                <XCircle className="h-4 w-4 mr-2" />
                Kuendigen
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Archive Dialog */}
        <AlertDialog open={activeDialog === 'archive'} onOpenChange={(open) => !open && setActiveDialog(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Vertrag archivieren</AlertDialogTitle>
              <AlertDialogDescription>
                Moechten Sie den Vertrag "{contract.title}" archivieren?
                Der Vertrag bleibt im System, wird aber aus der aktiven Liste entfernt.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Abbrechen</AlertDialogCancel>
              <AlertDialogAction onClick={handleArchive}>
                <Archive className="h-4 w-4 mr-2" />
                Archivieren
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Delete Dialog */}
        <AlertDialog open={activeDialog === 'delete'} onOpenChange={(open) => !open && setActiveDialog(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Vertrag loeschen</AlertDialogTitle>
              <AlertDialogDescription>
                Moechten Sie den Vertrag "{contract.title}" ({contract.contract_number}) wirklich loeschen?
                Diese Aktion kann nicht rueckgaengig gemacht werden.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Abbrechen</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleDelete}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Loeschen
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </>
    );
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" disabled={isLoading}>
            <MoreHorizontal className="h-4 w-4" />
            <span className="sr-only">Aktionen oeffnen</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuLabel>Aktionen</DropdownMenuLabel>
          <DropdownMenuSeparator />

          {onView && (
            <DropdownMenuItem onClick={() => onView(contract)}>
              <Eye className="h-4 w-4 mr-2" />
              Ansehen
            </DropdownMenuItem>
          )}

          {onEdit && (
            <DropdownMenuItem onClick={() => onEdit(contract)}>
              <FileEdit className="h-4 w-4 mr-2" />
              Bearbeiten
            </DropdownMenuItem>
          )}

          {onSendReminder && (
            <DropdownMenuItem onClick={handleSendReminder}>
              <Bell className="h-4 w-4 mr-2" />
              Erinnerung senden
            </DropdownMenuItem>
          )}

          <DropdownMenuSeparator />

          {canRenew && onRenew && (
            <DropdownMenuItem onClick={() => setActiveDialog('renew')}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Verlaengern
            </DropdownMenuItem>
          )}

          {canTerminate && onTerminate && (
            <DropdownMenuItem
              onClick={() => setActiveDialog('terminate')}
              className="text-red-600 focus:text-red-600"
            >
              <XCircle className="h-4 w-4 mr-2" />
              Kuendigen
            </DropdownMenuItem>
          )}

          {canArchive && onArchive && (
            <DropdownMenuItem onClick={() => setActiveDialog('archive')}>
              <Archive className="h-4 w-4 mr-2" />
              Archivieren
            </DropdownMenuItem>
          )}

          {onDelete && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => setActiveDialog('delete')}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Loeschen
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {renderDialogs()}
    </>
  );
}

export default ContractQuickActions;
