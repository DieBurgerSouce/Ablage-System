/**
 * BulkActionDialog
 *
 * Enterprise-Level Dialog für Bulk-Operationen auf Jobs.
 * Zeigt Anzahl, Warnung bei großer Anzahl, und Fortschritt während der Ausführung.
 */

import { useState, useCallback, useEffect } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, RotateCcw, Trash2, XCircle, Pause, Play } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

// ==================== Types ====================

export type BulkActionType = 'cancel' | 'retry' | 'pause' | 'resume' | 'delete';

interface BulkActionResult {
  success: number;
  failed: number;
  errors?: string[];
}

interface BulkActionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actionType: BulkActionType;
  selectedCount: number;
  onConfirm: () => Promise<BulkActionResult | void>;
  isLoading?: boolean;
}

// ==================== Constants ====================

const WARNING_THRESHOLD = 50;

const ACTION_CONFIG: Record<BulkActionType, {
  title: string;
  description: string;
  warningMessage: string;
  buttonText: string;
  buttonLoadingText: string;
  successText: string;
  icon: React.ReactNode;
  iconColor: string;
  buttonVariant: 'default' | 'destructive' | 'outline' | 'secondary';
}> = {
  cancel: {
    title: 'Jobs abbrechen',
    description: 'Alle ausgewählten Jobs werden abgebrochen.',
    warningMessage: 'Das Abbrechen vieler Jobs kann laufende Verarbeitungen unterbrechen.',
    buttonText: 'Jobs abbrechen',
    buttonLoadingText: 'Breche ab...',
    successText: 'Jobs abgebrochen',
    icon: <XCircle className="h-5 w-5" />,
    iconColor: 'text-destructive',
    buttonVariant: 'destructive',
  },
  retry: {
    title: 'Jobs wiederholen',
    description: 'Alle ausgewählten Jobs werden erneut gestartet.',
    warningMessage: 'Das Wiederholen vieler Jobs kann die Warteschlange stark belasten.',
    buttonText: 'Jobs wiederholen',
    buttonLoadingText: 'Starte erneut...',
    successText: 'Jobs gestartet',
    icon: <RotateCcw className="h-5 w-5" />,
    iconColor: 'text-blue-600',
    buttonVariant: 'default',
  },
  pause: {
    title: 'Jobs pausieren',
    description: 'Alle ausgewählten Jobs werden pausiert.',
    warningMessage: 'Pausierte Jobs verbleiben in der Warteschlange.',
    buttonText: 'Jobs pausieren',
    buttonLoadingText: 'Pausiere...',
    successText: 'Jobs pausiert',
    icon: <Pause className="h-5 w-5" />,
    iconColor: 'text-yellow-600',
    buttonVariant: 'secondary',
  },
  resume: {
    title: 'Jobs fortsetzen',
    description: 'Alle ausgewählten pausierten Jobs werden fortgesetzt.',
    warningMessage: 'Fortgesetzte Jobs werden sofort verarbeitet.',
    buttonText: 'Jobs fortsetzen',
    buttonLoadingText: 'Setze fort...',
    successText: 'Jobs fortgesetzt',
    icon: <Play className="h-5 w-5" />,
    iconColor: 'text-green-600',
    buttonVariant: 'default',
  },
  delete: {
    title: 'Jobs löschen',
    description: 'Alle ausgewählten Jobs werden permanent gelöscht.',
    warningMessage: 'Gelöschte Jobs können nicht wiederhergestellt werden!',
    buttonText: 'Jobs löschen',
    buttonLoadingText: 'Lösche...',
    successText: 'Jobs gelöscht',
    icon: <Trash2 className="h-5 w-5" />,
    iconColor: 'text-destructive',
    buttonVariant: 'destructive',
  },
};

// ==================== Component ====================

export function BulkActionDialog({
  open,
  onOpenChange,
  actionType,
  selectedCount,
  onConfirm,
  isLoading = false,
}: BulkActionDialogProps) {
  const [result, setResult] = useState<BulkActionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  const config = ACTION_CONFIG[actionType];
  const showWarning = selectedCount >= WARNING_THRESHOLD;
  const isCompleted = result !== null;

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setResult(null);
      setError(null);
      setProgress(0);
    }
  }, [open]);

  // Simulate progress during loading with proper completion handling
  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;

    if (isLoading && !isCompleted) {
      // Animate progress up to 90% during loading
      interval = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 90) return prev;
          return prev + Math.random() * 10;
        });
      }, 200);
    } else if (isCompleted) {
      // Operation complete - set to 100%
      setProgress(100);
    } else if (!isLoading && progress > 0 && progress < 100 && !isCompleted) {
      // isLoading became false but no result yet - animate to 95% and wait
      // This handles the race condition between isLoading=false and result being set
      setProgress(95);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isLoading, isCompleted, progress]);

  const handleConfirm = useCallback(async () => {
    setError(null);
    setProgress(0);
    try {
      const actionResult = await onConfirm();
      if (actionResult) {
        setResult(actionResult);
      } else {
        // If no result returned, assume all succeeded
        setResult({ success: selectedCount, failed: 0 });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ein unbekannter Fehler ist aufgetreten');
    }
  }, [onConfirm, selectedCount]);

  const handleClose = useCallback(() => {
    if (!isLoading) {
      onOpenChange(false);
    }
  }, [isLoading, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[450px]">
        <DialogHeader>
          <DialogTitle className={`flex items-center gap-2 ${config.iconColor}`}>
            {config.icon}
            {config.title}
          </DialogTitle>
          <DialogDescription>{config.description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Job Count Display */}
          <div className="flex items-center justify-center p-4 bg-muted rounded-lg">
            <div className="text-center">
              <div className="text-4xl font-bold">{selectedCount}</div>
              <div className="text-sm text-muted-foreground">
                {selectedCount === 1 ? 'Job ausgewählt' : 'Jobs ausgewählt'}
              </div>
            </div>
          </div>

          {/* Warning for large selections */}
          {showWarning && !isCompleted && (
            <Alert variant="default" className="border-yellow-500/50 bg-yellow-50/50 dark:bg-yellow-950/20">
              <AlertTriangle className="h-4 w-4 text-yellow-600" />
              <AlertTitle className="text-yellow-700 dark:text-yellow-500">Warnung</AlertTitle>
              <AlertDescription className="text-yellow-700 dark:text-yellow-500">
                {config.warningMessage}
              </AlertDescription>
            </Alert>
          )}

          {/* Progress Bar */}
          {(isLoading || isCompleted) && (
            <div className="space-y-2">
              <Progress value={progress} className="h-2" />
              <p className="text-sm text-muted-foreground text-center">
                {isLoading ? `${Math.round(progress)}% abgeschlossen...` : 'Abgeschlossen'}
              </p>
            </div>
          )}

          {/* Result Summary */}
          {isCompleted && result && (
            <Alert
              variant={result.failed === 0 ? 'default' : 'destructive'}
              className={result.failed === 0 ? 'border-green-500/50 bg-green-50/50 dark:bg-green-950/20' : ''}
            >
              {result.failed === 0 ? (
                <CheckCircle2 className="h-4 w-4 text-green-600" />
              ) : (
                <AlertTriangle className="h-4 w-4" />
              )}
              <AlertTitle>
                {result.failed === 0 ? 'Erfolgreich' : 'Teilweise erfolgreich'}
              </AlertTitle>
              <AlertDescription>
                <div className="flex gap-4 mt-2">
                  <div className="flex items-center gap-1">
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                    <span className="font-medium">{result.success}</span> erfolgreich
                  </div>
                  {result.failed > 0 && (
                    <div className="flex items-center gap-1">
                      <XCircle className="h-4 w-4 text-destructive" />
                      <span className="font-medium">{result.failed}</span> fehlgeschlagen
                    </div>
                  )}
                </div>
                {result.errors && result.errors.length > 0 && (
                  <ul className="mt-2 text-sm list-disc list-inside">
                    {result.errors.slice(0, 3).map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                    {result.errors.length > 3 && (
                      <li className="text-muted-foreground">
                        ... und {result.errors.length - 3} weitere Fehler
                      </li>
                    )}
                  </ul>
                )}
              </AlertDescription>
            </Alert>
          )}

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
          {isCompleted ? (
            <Button onClick={handleClose}>Schließen</Button>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={handleClose}
                disabled={isLoading}
              >
                Abbrechen
              </Button>
              <Button
                variant={config.buttonVariant}
                onClick={handleConfirm}
                disabled={isLoading || selectedCount === 0}
                className="gap-2"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {config.buttonLoadingText}
                  </>
                ) : (
                  <>
                    {config.icon}
                    {config.buttonText}
                  </>
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default BulkActionDialog;
