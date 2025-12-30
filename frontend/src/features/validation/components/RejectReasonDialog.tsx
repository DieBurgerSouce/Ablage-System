/**
 * RejectReasonDialog
 *
 * Dialog zur Eingabe des Ablehnungsgrundes mit Kategorieauswahl.
 * Wird sowohl für Einzel- als auch Batch-Ablehnungen verwendet.
 */

import { useState, useCallback } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  RejectionCategory,
  REJECTION_CATEGORY_LABELS,
} from '../types/validation-queue.types';

interface RejectReasonDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason: string, category?: RejectionCategory) => void;
  isLoading?: boolean;
  itemCount?: number; // Fuer Batch-Anzeige
  documentName?: string; // Fuer Einzel-Anzeige
}

export function RejectReasonDialog({
  open,
  onOpenChange,
  onConfirm,
  isLoading = false,
  itemCount,
  documentName,
}: RejectReasonDialogProps) {
  const [reason, setReason] = useState('');
  const [category, setCategory] = useState<RejectionCategory | ''>('');

  const handleConfirm = useCallback(() => {
    if (!reason.trim()) return;
    onConfirm(reason.trim(), category || undefined);
    setReason('');
    setCategory('');
  }, [reason, category, onConfirm]);

  const handleClose = useCallback(() => {
    if (!isLoading) {
      onOpenChange(false);
      setReason('');
      setCategory('');
    }
  }, [isLoading, onOpenChange]);

  const isBatch = itemCount !== undefined && itemCount > 1;
  const title = isBatch
    ? `${itemCount} Dokumente ablehnen`
    : documentName
      ? `"${documentName}" ablehnen`
      : 'Dokument ablehnen';

  const description = isBatch
    ? `Sie sind dabei, ${itemCount} Dokumente abzulehnen. Bitte geben Sie einen Grund an.`
    : 'Bitte geben Sie einen Grund für die Ablehnung an.';

  const hasError = !reason.trim() && reason.length > 0;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent
        className="sm:max-w-[500px]"
        aria-describedby="reject-dialog-description"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-destructive" aria-hidden="true" />
            {title}
          </DialogTitle>
          <DialogDescription id="reject-dialog-description">
            {description}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="rejection-category">Kategorie</Label>
            <Select
              value={category}
              onValueChange={(value) => setCategory(value as RejectionCategory)}
            >
              <SelectTrigger
                id="rejection-category"
                aria-label="Ablehnungskategorie auswählen"
              >
                <SelectValue placeholder="Kategorie auswählen (optional)" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(REJECTION_CATEGORY_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="rejection-reason">
              Grund <span className="text-destructive" aria-hidden="true">*</span>
              <span className="sr-only">(Pflichtfeld)</span>
            </Label>
            <Textarea
              id="rejection-reason"
              placeholder="Beschreiben Sie den Ablehnungsgrund..."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="min-h-[120px]"
              aria-required="true"
              aria-invalid={hasError}
              aria-describedby="rejection-reason-hint rejection-reason-error"
              autoFocus
            />
            <p id="rejection-reason-hint" className="text-xs text-muted-foreground">
              Der Grund wird für die Dokumentation und Nachverfolgung gespeichert.
            </p>
            {hasError && (
              <p
                id="rejection-reason-error"
                className="text-xs text-destructive"
                role="alert"
                aria-live="polite"
              >
                Bitte geben Sie einen Ablehnungsgrund ein.
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={isLoading}
            aria-label="Dialog schließen ohne Ablehnung"
          >
            Abbrechen
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={isLoading || !reason.trim()}
            aria-label={
              isBatch
                ? `${itemCount} Dokumente ablehnen`
                : documentName
                  ? `Dokument "${documentName}" ablehnen`
                  : 'Dokument ablehnen'
            }
            aria-busy={isLoading}
          >
            {isLoading ? 'Ablehnen...' : isBatch ? `${itemCount} ablehnen` : 'Ablehnen'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default RejectReasonDialog;
