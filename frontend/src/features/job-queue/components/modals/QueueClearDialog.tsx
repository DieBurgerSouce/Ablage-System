/**
 * QueueClearDialog - Security Critical
 *
 * Enterprise-Level Sicherheitsdialog für das Löschen aller Jobs aus einer Queue.
 * Erfordert explizite User-Bestätigung durch:
 * 1. Checkbox: "Ich verstehe, dass dies nicht rückgängig gemacht werden kann"
 * 2. Input-Feld: User MUSS "LÖSCHEN" tippen (exakte Übereinstimmung)
 */

import { useState, useCallback } from 'react';
import {
  AlertTriangle,
  Loader2,
  Skull,
  Trash2,
  XCircle,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

// ==================== Types ====================

export type QueueClearType = 'dlq' | 'queue' | 'all-queued';

interface QueueClearDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  type: QueueClearType;
  queueName?: string;
  itemCount: number;
  onConfirm: () => Promise<void>;
  isLoading?: boolean;
}

// ==================== Constants ====================

const CONFIRMATION_WORD = 'LÖSCHEN';

const TYPE_CONFIG: Record<QueueClearType, {
  title: string;
  description: string;
  warningTitle: string;
  warningDescription: string;
  icon: React.ReactNode;
  buttonText: string;
}> = {
  dlq: {
    title: 'Dead Letter Queue leeren',
    description: 'Alle fehlgeschlagenen Tasks aus der Dead Letter Queue entfernen.',
    warningTitle: 'Unwiderrufliche Aktion',
    warningDescription: 'Alle fehlgeschlagenen Tasks werden permanent gelöscht. Fehleranalyse und Wiederholung sind danach nicht mehr möglich.',
    icon: <Skull className="h-5 w-5" />,
    buttonText: 'DLQ leeren',
  },
  queue: {
    title: 'Queue leeren',
    description: 'Alle wartenden Jobs aus dieser Queue entfernen.',
    warningTitle: 'Produktive Jobs betroffen',
    warningDescription: 'Alle wartenden Jobs werden abgebrochen. Dokumente müssen erneut zur Verarbeitung eingereicht werden.',
    icon: <Trash2 className="h-5 w-5" />,
    buttonText: 'Queue leeren',
  },
  'all-queued': {
    title: 'Alle Warteschlangen leeren',
    description: 'Alle wartenden Jobs aus ALLEN Queues entfernen.',
    warningTitle: 'Kritische Systemoperation',
    warningDescription: 'ALLE wartenden Jobs im System werden abgebrochen. Diese Aktion sollte nur in Notfällen durchgeführt werden.',
    icon: <AlertTriangle className="h-5 w-5" />,
    buttonText: 'Alle Queues leeren',
  },
};

// ==================== Component ====================

export function QueueClearDialog({
  open,
  onOpenChange,
  type,
  queueName,
  itemCount,
  onConfirm,
  isLoading = false,
}: QueueClearDialogProps) {
  const [understoodChecked, setUnderstoodChecked] = useState(false);
  const [confirmationText, setConfirmationText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const config = TYPE_CONFIG[type];

  // Reset state when dialog closes
  const handleOpenChange = useCallback((newOpen: boolean) => {
    if (!newOpen) {
      setUnderstoodChecked(false);
      setConfirmationText('');
      setError(null);
    }
    onOpenChange(newOpen);
  }, [onOpenChange]);

  // Check if confirmation is valid
  const isConfirmationValid = confirmationText.trim().toUpperCase() === CONFIRMATION_WORD;
  const canConfirm = understoodChecked && isConfirmationValid && !isLoading;

  // Handle confirm action
  const handleConfirm = useCallback(async () => {
    if (!canConfirm) return;

    setError(null);
    try {
      await onConfirm();
      handleOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ein unbekannter Fehler ist aufgetreten');
    }
  }, [canConfirm, onConfirm, handleOpenChange]);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            {config.icon}
            {config.title}
            {queueName && `: ${queueName}`}
          </DialogTitle>
          <DialogDescription>{config.description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Critical Warning Banner */}
          <Alert variant="destructive" className="border-2">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle className="font-bold">{config.warningTitle}</AlertTitle>
            <AlertDescription className="mt-2">
              <p>{config.warningDescription}</p>
              <p className="mt-2 font-bold text-lg">
                {itemCount} {itemCount === 1 ? 'Element wird' : 'Elemente werden'} unwiderruflich gelöscht!
              </p>
            </AlertDescription>
          </Alert>

          {/* Understanding Checkbox */}
          <div className="flex items-start space-x-3 rounded-lg border-2 border-destructive/50 bg-destructive/5 p-4">
            <Checkbox
              id="understand"
              checked={understoodChecked}
              onCheckedChange={(checked) => setUnderstoodChecked(checked === true)}
              disabled={isLoading}
              className="mt-0.5"
            />
            <Label
              htmlFor="understand"
              className="text-sm font-medium leading-none cursor-pointer"
            >
              Ich verstehe, dass diese Aktion{' '}
              <span className="font-bold text-destructive">NICHT rückgängig</span>{' '}
              gemacht werden kann und alle betroffenen Daten permanent verloren gehen.
            </Label>
          </div>

          {/* Confirmation Input */}
          <div className="space-y-2">
            <Label htmlFor="confirmation" className="text-sm font-medium">
              Bitte tippen Sie <span className="font-bold text-destructive">"{CONFIRMATION_WORD}"</span> zur Bestätigung:
            </Label>
            <Input
              id="confirmation"
              type="text"
              value={confirmationText}
              onChange={(e) => setConfirmationText(e.target.value)}
              placeholder={CONFIRMATION_WORD}
              disabled={isLoading}
              className={`font-mono text-lg ${
                confirmationText.length > 0
                  ? isConfirmationValid
                    ? 'border-green-500 focus:ring-green-500'
                    : 'border-red-500 focus:ring-red-500'
                  : ''
              }`}
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
            />
            {confirmationText.length > 0 && !isConfirmationValid && (
              <p className="text-xs text-destructive flex items-center gap-1">
                <XCircle className="h-3 w-3" />
                Bestätigungswort stimmt nicht überein
              </p>
            )}
          </div>

          {/* Error Message */}
          {error && (
            <Alert variant="destructive">
              <XCircle className="h-4 w-4" />
              <AlertTitle>Fehler</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter className="flex gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isLoading}
          >
            Abbrechen
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={!canConfirm}
            className="gap-2"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Wird gelöscht...
              </>
            ) : (
              <>
                <Trash2 className="h-4 w-4" />
                {config.buttonText}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default QueueClearDialog;
