/**
 * BulkApproveDialog
 *
 * Bestätigungsdialog für Batch-Genehmigungen mit Zusammenfassung.
 * Zeigt eine Übersicht der zu genehmigenden Items.
 */

import { useState, useCallback } from 'react';
import { CheckCircle, FileText, AlertTriangle } from 'lucide-react';
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
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { ValidationQueueItem } from '../types/validation-queue.types';

interface BulkApproveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (notes?: string, applyCorrections?: boolean) => void;
  isLoading?: boolean;
  items: ValidationQueueItem[];
}

export function BulkApproveDialog({
  open,
  onOpenChange,
  onConfirm,
  isLoading = false,
  items,
}: BulkApproveDialogProps) {
  const [notes, setNotes] = useState('');
  const [applyCorrections, setApplyCorrections] = useState(true);

  const handleConfirm = useCallback(() => {
    onConfirm(notes.trim() || undefined, applyCorrections);
    setNotes('');
    setApplyCorrections(true);
  }, [notes, applyCorrections, onConfirm]);

  const handleClose = useCallback(() => {
    if (!isLoading) {
      onOpenChange(false);
      setNotes('');
      setApplyCorrections(true);
    }
  }, [isLoading, onOpenChange]);

  // Statistiken berechnen
  const totalCorrections = items.reduce((sum, item) => sum + item.corrections_made, 0);
  const avgConfidence =
    items.length > 0
      ? items.reduce((sum, item) => sum + (item.avg_field_confidence || 0), 0) / items.length
      : 0;
  const lowConfidenceItems = items.filter(
    (item) => item.avg_field_confidence !== null && item.avg_field_confidence < 0.7
  );

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent
        className="sm:max-w-[550px]"
        aria-describedby="bulk-approve-description"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-green-600" aria-hidden="true" />
            {items.length} Dokumente genehmigen
          </DialogTitle>
          <DialogDescription id="bulk-approve-description">
            Bitte überprüfen Sie die Zusammenfassung vor der Genehmigung.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Screen Reader: Zusammenfassung */}
          <div className="sr-only" aria-live="polite">
            Batch-Genehmigung: {items.length} Dokumente mit insgesamt {totalCorrections} Korrekturen.
            Durchschnittliche Konfidenz: {avgConfidence > 0 ? `${Math.round(avgConfidence * 100)} Prozent` : 'nicht verfügbar'}.
            {lowConfidenceItems.length > 0 && ` Warnung: ${lowConfidenceItems.length} Dokumente haben eine niedrige Konfidenz.`}
          </div>

          {/* Statistik-Karten */}
          <div className="grid grid-cols-3 gap-3" role="group" aria-label="Batch-Statistiken">
            <div className="p-3 bg-muted/30 rounded-md text-center">
              <div className="text-2xl font-bold" aria-hidden="true">{items.length}</div>
              <div className="text-xs text-muted-foreground">Dokumente</div>
            </div>
            <div className="p-3 bg-muted/30 rounded-md text-center">
              <div className="text-2xl font-bold" aria-hidden="true">{totalCorrections}</div>
              <div className="text-xs text-muted-foreground">Korrekturen</div>
            </div>
            <div className="p-3 bg-muted/30 rounded-md text-center">
              <div className="text-2xl font-bold" aria-hidden="true">
                {avgConfidence > 0 ? `${Math.round(avgConfidence * 100)}%` : '-'}
              </div>
              <div className="text-xs text-muted-foreground">Durchschn. Konfidenz</div>
            </div>
          </div>

          {/* Warnung bei niedriger Konfidenz */}
          {lowConfidenceItems.length > 0 && (
            <div
              className="flex items-start gap-2 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md"
              role="alert"
              aria-live="polite"
            >
              <AlertTriangle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
              <div>
                <p className="text-sm font-medium text-yellow-800 dark:text-yellow-200">
                  {lowConfidenceItems.length} Dokument(e) mit niedriger Konfidenz
                </p>
                <p className="text-xs text-yellow-700 dark:text-yellow-300 mt-1">
                  Diese Dokumente haben eine durchschnittliche Konfidenz unter 70%.
                  Bitte stellen Sie sicher, dass die Daten korrekt sind.
                </p>
              </div>
            </div>
          )}

          {/* Dokument-Liste */}
          <div className="space-y-2">
            <Label>Dokumente</Label>
            <ScrollArea className="h-[150px] border rounded-md">
              <div className="p-2 space-y-1">
                {items.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between p-2 hover:bg-muted/50 rounded"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                      <span className="text-sm truncate">
                        {item.document_name || `Dokument ${item.document_id.slice(0, 8)}`}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {item.corrections_made > 0 && (
                        <Badge variant="outline" className="text-xs">
                          {item.corrections_made} Korr.
                        </Badge>
                      )}
                      {item.avg_field_confidence !== null && (
                        <Badge
                          variant={item.avg_field_confidence >= 0.7 ? 'secondary' : 'destructive'}
                          className="text-xs"
                        >
                          {Math.round(item.avg_field_confidence * 100)}%
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>

          {/* Optionen */}
          <div className="flex items-center space-x-2">
            <Checkbox
              id="apply-corrections"
              checked={applyCorrections}
              onCheckedChange={(checked) => setApplyCorrections(checked as boolean)}
              aria-describedby="apply-corrections-hint"
            />
            <Label htmlFor="apply-corrections" className="text-sm font-normal">
              Korrekturen auf Originaldokumente anwenden
            </Label>
          </div>
          <p id="apply-corrections-hint" className="sr-only">
            Wenn aktiviert, werden alle vorgenommenen Korrekturen auf die Originaldokumente übertragen.
          </p>

          {/* Notizen */}
          <div className="space-y-2">
            <Label htmlFor="approval-notes">Notizen (optional)</Label>
            <Textarea
              id="approval-notes"
              placeholder="Optionale Anmerkungen zur Batch-Genehmigung..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="min-h-[80px]"
              aria-describedby="approval-notes-hint"
            />
            <p id="approval-notes-hint" className="sr-only">
              Optionale Notizen zur Dokumentation der Batch-Genehmigung.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={isLoading}
            aria-label="Dialog schließen ohne Genehmigung"
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={isLoading || items.length === 0}
            className="bg-green-600 hover:bg-green-700"
            aria-label={`${items.length} Dokumente genehmigen`}
            aria-busy={isLoading}
          >
            {isLoading ? 'Genehmigen...' : `${items.length} Dokumente genehmigen`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default BulkApproveDialog;
