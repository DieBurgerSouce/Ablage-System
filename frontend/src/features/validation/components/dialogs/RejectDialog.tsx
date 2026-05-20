/**
 * RejectDialog
 *
 * Dialog zur Ablehnung eines Training-Samples.
 * Begründung ist Pflicht.
 */

import { useState } from 'react';
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
import { X, AlertTriangle } from 'lucide-react';

interface RejectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason: string) => Promise<void>;
  isLoading?: boolean;
  documentName: string;
}

export function RejectDialog({
  open,
  onOpenChange,
  onConfirm,
  isLoading,
  documentName,
}: RejectDialogProps) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');

  const handleConfirm = async () => {
    if (!reason.trim()) {
      setError('Bitte geben Sie eine Begründung an.');
      return;
    }
    if (reason.trim().length < 10) {
      setError('Die Begründung muss mindestens 10 Zeichen lang sein.');
      return;
    }
    setError('');
    await onConfirm(reason);
    setReason('');
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setReason('');
      setError('');
    }
    onOpenChange(open);
  };

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-destructive">
            <X className="w-5 h-5" />
            Sample ablehnen
          </AlertDialogTitle>
          <AlertDialogDescription>
            Möchten Sie das Sample &quot;{documentName}&quot; ablehnen?
            Bitte geben Sie eine Begründung an.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="py-4 space-y-2">
          <Label htmlFor="reject-reason" className="flex items-center gap-1">
            Begründung
            <span className="text-destructive">*</span>
          </Label>
          <Textarea
            id="reject-reason"
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (error) setError('');
            }}
            placeholder="Warum wird dieses Sample abgelehnt..."
            rows={4}
            className={error ? 'border-destructive' : ''}
          />
          {error && (
            <div className="flex items-center gap-1 text-sm text-destructive">
              <AlertTriangle className="w-3 h-3" />
              {error}
            </div>
          )}
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>Abbrechen</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={isLoading || !reason.trim()}
            className="bg-destructive hover:bg-destructive/90"
          >
            {isLoading ? 'Ablehnen...' : 'Ablehnen'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
