/**
 * CorrectionDialog Component
 *
 * Dialog fuer Inline-Korrektur eines OCR-Feldes.
 * Zeigt Original-Wert und erlaubt Eingabe des korrigierten Werts.
 */

import { useState, useEffect } from 'react';
import { CheckCircle2, X, Loader2, AlertTriangle, Sparkles, ArrowRight } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { cn } from '@/lib/utils';
import { useSubmitCorrection } from '../hooks/use-ocr-feedback';
import type { QueueItem, CorrectionRequest, CorrectionResult } from '../api/ocr-feedback-api';
import { toast } from 'sonner';

interface CorrectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: QueueItem | null;
  onSuccess?: (result: CorrectionResult) => void;
}

type CorrectionType = 'text' | 'amount' | 'date' | 'entity' | 'iban' | 'vat_id' | 'reference';

const correctionTypeLabels: Record<CorrectionType, { label: string; points: number }> = {
  text: { label: 'Text', points: 10 },
  amount: { label: 'Betrag', points: 15 },
  date: { label: 'Datum', points: 12 },
  entity: { label: 'Firma/Person', points: 20 },
  iban: { label: 'IBAN', points: 25 },
  vat_id: { label: 'USt-ID', points: 25 },
  reference: { label: 'Referenz', points: 15 },
};

// Automatische Erkennung des Korrektur-Typs basierend auf Feldname
function detectCorrectionType(fieldName: string): CorrectionType {
  const field = fieldName.toLowerCase();

  if (field.includes('iban') || field.includes('konto')) return 'iban';
  if (field.includes('ust') || field.includes('vat') || field.includes('steuernummer')) return 'vat_id';
  if (field.includes('betrag') || field.includes('amount') || field.includes('summe') || field.includes('total')) return 'amount';
  if (field.includes('datum') || field.includes('date')) return 'date';
  if (field.includes('firma') || field.includes('company') || field.includes('kunde') || field.includes('lieferant')) return 'entity';
  if (field.includes('referenz') || field.includes('reference') || field.includes('nummer') || field.includes('number')) return 'reference';

  return 'text';
}

export function CorrectionDialog({ open, onOpenChange, item, onSuccess }: CorrectionDialogProps) {
  const [correctedValue, setCorrectedValue] = useState('');
  const [correctionType, setCorrectionType] = useState<CorrectionType>('text');
  const [showSuccess, setShowSuccess] = useState(false);
  const [lastResult, setLastResult] = useState<CorrectionResult | null>(null);

  const { mutate: submitCorrection, isPending, error, reset } = useSubmitCorrection();

  // Reset beim Oeffnen
  useEffect(() => {
    if (open && item) {
      setCorrectedValue(item.suggested_value || item.ocr_value || '');
      setCorrectionType(detectCorrectionType(item.field_name));
      setShowSuccess(false);
      setLastResult(null);
      reset();
    }
  }, [open, item, reset]);

  const handleSubmit = () => {
    if (!item || !correctedValue.trim()) return;

    const request: CorrectionRequest = {
      document_id: item.document_id,
      field_name: item.field_name,
      original_value: item.ocr_value,
      corrected_value: correctedValue.trim(),
      confidence_before: item.confidence,
      correction_type: correctionType,
      ocr_backend: item.ocr_backend,
      page_number: item.page_number || undefined,
    };

    submitCorrection(request, {
      onSuccess: (result) => {
        setLastResult(result);
        setShowSuccess(true);
        toast.success(result.feedback_message);

        // Nach kurzer Verzoegerung schliessen
        setTimeout(() => {
          onSuccess?.(result);
        }, 1500);
      },
      onError: (err) => {
        toast.error('Korrektur konnte nicht gespeichert werden.');
      },
    });
  };

  if (!item) return null;

  const expectedPoints = correctionTypeLabels[correctionType].points;
  const isMultiline = item.ocr_value.length > 100 || item.ocr_value.includes('\n');

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        {showSuccess && lastResult ? (
          // Erfolgs-Ansicht
          <div className="py-8 text-center space-y-4">
            <div className="flex justify-center">
              <div className="w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center">
                <CheckCircle2 className="w-10 h-10 text-green-500" />
              </div>
            </div>
            <div>
              <h3 className="text-xl font-bold">Korrektur gespeichert!</h3>
              <p className="text-muted-foreground mt-1">{lastResult.feedback_message}</p>
            </div>
            <div className="flex justify-center gap-6 text-center">
              <div>
                <div className="text-2xl font-bold text-primary">+{lastResult.total_points}</div>
                <div className="text-xs text-muted-foreground">Punkte</div>
              </div>
              {lastResult.new_streak > 0 && (
                <div>
                  <div className="text-2xl font-bold text-orange-500">{lastResult.new_streak}</div>
                  <div className="text-xs text-muted-foreground">Tage Streak</div>
                </div>
              )}
              <div>
                <div className="text-2xl font-bold">{lastResult.new_user_total.toLocaleString('de-DE')}</div>
                <div className="text-xs text-muted-foreground">Gesamt</div>
              </div>
            </div>
            {lastResult.achievements_unlocked.length > 0 && (
              <div className="flex justify-center gap-2">
                {lastResult.achievements_unlocked.map((ach) => (
                  <Badge key={ach} variant="default" className="animate-pulse">
                    <Sparkles className="w-3 h-3 mr-1" />
                    Neues Achievement!
                  </Badge>
                ))}
              </div>
            )}
          </div>
        ) : (
          // Korrektur-Formular
          <>
            <DialogHeader>
              <DialogTitle>OCR-Korrektur</DialogTitle>
              <DialogDescription>
                Korrigieren Sie den erkannten Wert fuer das Feld "{item.field_name}".
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              {/* Dokument-Info */}
              <div className="text-sm text-muted-foreground">
                <span className="font-medium">{item.document_filename}</span>
                {item.entity_name && (
                  <span className="ml-2">({item.entity_name})</span>
                )}
              </div>

              {/* Original-Wert */}
              <div className="space-y-2">
                <Label className="text-muted-foreground">Original (OCR)</Label>
                <div className="p-3 rounded-md bg-muted font-mono text-sm whitespace-pre-wrap break-all">
                  {item.ocr_value || <span className="text-muted-foreground italic">Leer</span>}
                </div>
              </div>

              {/* Pfeil */}
              <div className="flex justify-center">
                <ArrowRight className="w-5 h-5 text-muted-foreground" />
              </div>

              {/* Korrektur-Typ */}
              <div className="space-y-2">
                <Label htmlFor="correction-type">Korrektur-Typ</Label>
                <Select
                  value={correctionType}
                  onValueChange={(v) => setCorrectionType(v as CorrectionType)}
                >
                  <SelectTrigger id="correction-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(correctionTypeLabels).map(([key, { label, points }]) => (
                      <SelectItem key={key} value={key}>
                        {label} ({points} Pkt.)
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Korrigierter Wert */}
              <div className="space-y-2">
                <Label htmlFor="corrected-value">Korrektur</Label>
                {isMultiline ? (
                  <Textarea
                    id="corrected-value"
                    value={correctedValue}
                    onChange={(e) => setCorrectedValue(e.target.value)}
                    placeholder="Korrigierten Wert eingeben..."
                    className="font-mono min-h-[100px]"
                    disabled={isPending}
                  />
                ) : (
                  <Input
                    id="corrected-value"
                    value={correctedValue}
                    onChange={(e) => setCorrectedValue(e.target.value)}
                    placeholder="Korrigierten Wert eingeben..."
                    className="font-mono"
                    disabled={isPending}
                    autoFocus
                  />
                )}
              </div>

              {/* Vorschlag */}
              {item.suggested_value && item.suggested_value !== correctedValue && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">
                    Vorschlag: <span className="font-mono">{item.suggested_value}</span>
                  </span>
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto p-0"
                    onClick={() => setCorrectedValue(item.suggested_value!)}
                  >
                    Uebernehmen
                  </Button>
                </div>
              )}

              {/* Punkte-Vorschau */}
              <div className="flex items-center justify-between text-sm bg-muted/50 p-2 rounded">
                <span className="text-muted-foreground">Erwartete Punkte</span>
                <Badge variant="secondary">~{expectedPoints}+ Punkte</Badge>
              </div>

              {/* Fehler */}
              {error && (
                <Alert variant="destructive">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    Korrektur konnte nicht gespeichert werden. Bitte erneut versuchen.
                  </AlertDescription>
                </Alert>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
                Abbrechen
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={!correctedValue.trim() || isPending}
              >
                {isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Speichern...
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4 mr-2" />
                    Korrektur speichern
                  </>
                )}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
