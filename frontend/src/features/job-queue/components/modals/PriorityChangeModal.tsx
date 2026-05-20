/**
 * PriorityChangeModal
 *
 * Enterprise-Level Modal für die Änderung der Job-Priorität.
 * Unterstützt einzelne und mehrere Jobs gleichzeitig.
 */

import { useState, useCallback, useEffect } from 'react';
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronUp,
  Loader2,
  Zap,
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
import { Badge } from '@/components/ui/badge';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface PriorityChangeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentPriority?: number;
  jobCount: number;
  onConfirm: (newPriority: number) => Promise<void>;
  isLoading?: boolean;
}

// ==================== Constants ====================

const PRIORITY_LEVELS = [
  { value: 1, label: 'Kritisch', description: 'Sofortige Verarbeitung', color: 'bg-red-500' },
  { value: 2, label: 'Dringend', description: 'Nächste in der Queue', color: 'bg-orange-500' },
  { value: 3, label: 'Hoch', description: 'Bevorzugte Verarbeitung', color: 'bg-yellow-500' },
  { value: 4, label: 'Erhöht', description: 'Leicht bevorzugt', color: 'bg-lime-500' },
  { value: 5, label: 'Normal', description: 'Standard-Priorität', color: 'bg-green-500' },
  { value: 6, label: 'Mittel', description: 'Unter Standard', color: 'bg-teal-500' },
  { value: 7, label: 'Niedrig', description: 'Hintergrundverarbeitung', color: 'bg-cyan-500' },
  { value: 8, label: 'Sehr niedrig', description: 'Wenn Zeit verfügbar', color: 'bg-blue-500' },
  { value: 9, label: 'Minimal', description: 'Letzte Priorität', color: 'bg-indigo-500' },
  { value: 10, label: 'Idle', description: 'Nur bei Leerlauf', color: 'bg-purple-500' },
];

// ==================== Component ====================

export function PriorityChangeModal({
  open,
  onOpenChange,
  currentPriority = 5,
  jobCount,
  onConfirm,
  isLoading = false,
}: PriorityChangeModalProps) {
  const [selectedPriority, setSelectedPriority] = useState(currentPriority);
  const [error, setError] = useState<string | null>(null);

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setSelectedPriority(currentPriority);
      setError(null);
    }
  }, [open, currentPriority]);

  const currentLevel = PRIORITY_LEVELS.find((l) => l.value === selectedPriority) || PRIORITY_LEVELS[4];
  const originalLevel = PRIORITY_LEVELS.find((l) => l.value === currentPriority);
  const hasChanged = selectedPriority !== currentPriority;

  const handleConfirm = useCallback(async () => {
    if (!hasChanged) {
      onOpenChange(false);
      return;
    }

    setError(null);
    try {
      await onConfirm(selectedPriority);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ein unbekannter Fehler ist aufgetreten');
    }
  }, [selectedPriority, hasChanged, onConfirm, onOpenChange]);

  const handleClose = useCallback(() => {
    if (!isLoading) {
      onOpenChange(false);
    }
  }, [isLoading, onOpenChange]);

  const incrementPriority = () => {
    if (selectedPriority > 1) {
      setSelectedPriority(selectedPriority - 1);
    }
  };

  const decrementPriority = () => {
    if (selectedPriority < 10) {
      setSelectedPriority(selectedPriority + 1);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[450px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-yellow-500" />
            Priorität ändern
          </DialogTitle>
          <DialogDescription>
            {jobCount === 1
              ? 'Ändern Sie die Priorität des ausgewählten Jobs.'
              : `Ändern Sie die Priorität von ${jobCount} ausgewählten Jobs.`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Current Priority Display */}
          {originalLevel && (
            <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
              <span className="text-sm text-muted-foreground">Aktuelle Priorität:</span>
              <Badge variant="outline" className="gap-1">
                <div className={cn('w-2 h-2 rounded-full', originalLevel.color)} />
                {originalLevel.value} - {originalLevel.label}
              </Badge>
            </div>
          )}

          {/* Priority Slider */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <Label>Neue Priorität</Label>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="icon"
                  onClick={incrementPriority}
                  disabled={selectedPriority <= 1 || isLoading}
                  className="h-8 w-8"
                >
                  <ChevronUp className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  onClick={decrementPriority}
                  disabled={selectedPriority >= 10 || isLoading}
                  className="h-8 w-8"
                >
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <Slider
              value={[selectedPriority]}
              onValueChange={(values) => setSelectedPriority(values[0])}
              min={1}
              max={10}
              step={1}
              disabled={isLoading}
              className="w-full"
            />

            {/* Priority Scale */}
            <div className="flex justify-between text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <ArrowUp className="h-3 w-3 text-red-500" />
                Höher (1)
              </span>
              <span className="flex items-center gap-1">
                Niedriger (10)
                <ArrowDown className="h-3 w-3 text-purple-500" />
              </span>
            </div>
          </div>

          {/* Selected Priority Display */}
          <div className={cn(
            'p-4 rounded-lg border-2 transition-colors',
            hasChanged ? 'border-primary bg-primary/5' : 'border-muted bg-muted'
          )}>
            <div className="flex items-center gap-3">
              <div className={cn('w-4 h-4 rounded-full', currentLevel.color)} />
              <div>
                <div className="font-semibold text-lg">
                  {currentLevel.value} - {currentLevel.label}
                </div>
                <div className="text-sm text-muted-foreground">
                  {currentLevel.description}
                </div>
              </div>
            </div>
          </div>

          {/* Priority Change Indicator */}
          {hasChanged && (
            <div className="flex items-center justify-center gap-2 text-sm">
              {selectedPriority < currentPriority ? (
                <>
                  <ArrowUp className="h-4 w-4 text-green-600" />
                  <span className="text-green-600 font-medium">
                    Priorität wird erhöht um {currentPriority - selectedPriority} Stufe(n)
                  </span>
                </>
              ) : (
                <>
                  <ArrowDown className="h-4 w-4 text-yellow-600" />
                  <span className="text-yellow-600 font-medium">
                    Priorität wird verringert um {selectedPriority - currentPriority} Stufe(n)
                  </span>
                </>
              )}
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="flex items-center gap-2 text-sm text-destructive p-3 bg-destructive/10 rounded-lg">
              <AlertCircle className="h-4 w-4" />
              {error}
            </div>
          )}
        </div>

        <DialogFooter className="flex gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={isLoading}
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={isLoading || !hasChanged}
            className="gap-2"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Speichere...
              </>
            ) : (
              <>
                <Zap className="h-4 w-4" />
                Priorität speichern
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default PriorityChangeModal;
