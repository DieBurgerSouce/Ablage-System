/**
 * Delegation Action Dialogs
 *
 * Confirmation dialogs for delegation actions (decline, revoke, extend)
 */

import { useState } from 'react';
import { AlertTriangle, Calendar } from 'lucide-react';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

interface DeclineDelegationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason?: string) => void;
  isLoading?: boolean;
}

export function DeclineDelegationDialog({
  open,
  onOpenChange,
  onConfirm,
  isLoading = false,
}: DeclineDelegationDialogProps) {
  const [reason, setReason] = useState('');

  const handleConfirm = () => {
    onConfirm(reason || undefined);
    setReason('');
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-orange-500" />
            Vertretung ablehnen
          </AlertDialogTitle>
          <AlertDialogDescription>
            Moechten Sie diese Vertretungsanfrage wirklich ablehnen? Der
            Anfragende wird ueber Ihre Ablehnung informiert.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="py-4">
          <Label>Grund der Ablehnung (optional)</Label>
          <Textarea
            className="mt-1.5"
            placeholder="z.B. Zeitlich nicht moeglich..."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>Abbrechen</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={isLoading}
            className="bg-orange-600 hover:bg-orange-700"
          >
            {isLoading ? 'Wird abgelehnt...' : 'Ablehnen'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

interface RevokeDelegationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason?: string) => void;
  isLoading?: boolean;
}

export function RevokeDelegationDialog({
  open,
  onOpenChange,
  onConfirm,
  isLoading = false,
}: RevokeDelegationDialogProps) {
  const [reason, setReason] = useState('');

  const handleConfirm = () => {
    onConfirm(reason || undefined);
    setReason('');
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            Vertretung widerrufen
          </AlertDialogTitle>
          <AlertDialogDescription>
            Moechten Sie diese Vertretung wirklich widerrufen? Der Vertreter
            verliert sofort alle uebertragenen Berechtigungen.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="py-4">
          <Label>Grund des Widerrufs (optional)</Label>
          <Textarea
            className="mt-1.5"
            placeholder="z.B. Fruehzeitige Rueckkehr..."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>Abbrechen</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={isLoading}
            className="bg-destructive hover:bg-destructive/90"
          >
            {isLoading ? 'Wird widerrufen...' : 'Widerrufen'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

interface ExtendDelegationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentEndDate: string;
  onConfirm: (newEndDate: string) => void;
  isLoading?: boolean;
}

export function ExtendDelegationDialog({
  open,
  onOpenChange,
  currentEndDate,
  onConfirm,
  isLoading = false,
}: ExtendDelegationDialogProps) {
  const [newEndDate, setNewEndDate] = useState('');

  // Set default new end date when dialog opens
  const handleOpenChange = (isOpen: boolean) => {
    if (isOpen && !newEndDate) {
      const current = new Date(currentEndDate);
      current.setDate(current.getDate() + 7); // Default: 7 days extension
      setNewEndDate(current.toISOString().split('T')[0]);
    }
    onOpenChange(isOpen);
  };

  const handleConfirm = () => {
    if (newEndDate) {
      onConfirm(newEndDate);
      setNewEndDate('');
    }
  };

  const isValid = newEndDate && new Date(newEndDate) > new Date(currentEndDate);

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5" />
            Vertretung verlaengern
          </AlertDialogTitle>
          <AlertDialogDescription>
            Aktuelles Enddatum:{' '}
            {new Date(currentEndDate).toLocaleDateString('de-DE')}. Waehlen Sie
            ein neues Enddatum.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="py-4">
          <Label>Neues Enddatum *</Label>
          <div className="relative mt-1.5">
            <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              type="date"
              value={newEndDate}
              onChange={(e) => setNewEndDate(e.target.value)}
              min={currentEndDate}
              className="pl-9"
            />
          </div>
          {newEndDate && !isValid && (
            <p className="text-sm text-destructive mt-1">
              Das neue Enddatum muss nach dem aktuellen liegen.
            </p>
          )}
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>Abbrechen</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={!isValid || isLoading}
          >
            {isLoading ? 'Wird verlaengert...' : 'Verlaengern'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
