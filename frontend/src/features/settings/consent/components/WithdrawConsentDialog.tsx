/**
 * WithdrawConsentDialog Component
 *
 * Bestätigung für den Widerruf einer Einwilligung mit optionalem Grund.
 */

import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
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
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import type { ConsentScope } from '../types';
import { CONSENT_SCOPE_LABELS } from '../types';

interface WithdrawConsentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scope: ConsentScope | null;
  onConfirm: (scope: ConsentScope, reason?: string) => void;
  isLoading?: boolean;
}

export function WithdrawConsentDialog({
  open,
  onOpenChange,
  scope,
  onConfirm,
  isLoading = false,
}: WithdrawConsentDialogProps) {
  const [reason, setReason] = useState('');

  const handleConfirm = () => {
    if (scope) {
      onConfirm(scope, reason.trim() || undefined);
      setReason('');
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      setReason('');
    }
    onOpenChange(newOpen);
  };

  const scopeLabel = scope ? CONSENT_SCOPE_LABELS[scope] : '';

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <AlertDialogTitle>Einwilligung widerrufen</AlertDialogTitle>
          </div>
          <AlertDialogDescription className="pt-2 space-y-3">
            <p>
              Möchten Sie Ihre Einwilligung für <strong>{scopeLabel}</strong> wirklich
              widerrufen?
            </p>
            <p>
              Nach dem Widerruf wird die Verarbeitung Ihrer Daten in diesem Bereich
              eingestellt. Sie können die Einwilligung jederzeit erneut erteilen.
            </p>
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="py-4">
          <Label htmlFor="withdraw-reason" className="text-sm font-medium">
            Grund für den Widerruf (optional)
          </Label>
          <Textarea
            id="withdraw-reason"
            placeholder="Warum möchten Sie die Einwilligung widerrufen?"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="mt-2"
            rows={3}
            maxLength={500}
          />
          <p className="text-xs text-muted-foreground mt-1">{reason.length}/500 Zeichen</p>
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>Abbrechen</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={isLoading}
            className="bg-amber-600 hover:bg-amber-700 focus:ring-amber-600"
          >
            {isLoading ? 'Wird widerrufen...' : 'Einwilligung widerrufen'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
