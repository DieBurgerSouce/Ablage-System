/**
 * Batch Correction Panel Component
 * Ermöglicht die Korrektur mehrerer Felder auf einmal
 */

import { useState, useEffect, useCallback } from 'react';
import { Save, RotateCcw, CheckCircle2, XCircle, Keyboard } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useToast } from '@/hooks/use-toast';
import { useSubmitBatchCorrections } from '../hooks';
import type {
  LowConfidenceDocument,
  LowConfidenceField,
  CorrectionSubmission,
  CorrectionType,
} from '../types';
import { CORRECTION_TYPE_LABELS, CORRECTION_TYPE_DESCRIPTIONS } from '../types';

interface BatchCorrectionPanelProps {
  document: LowConfidenceDocument | null;
  onCorrectionComplete?: () => void;
}

interface FieldCorrection {
  field: LowConfidenceField;
  correctedValue: string;
  correctionType: CorrectionType;
  isModified: boolean;
}

function getConfidenceColor(confidence: number): string {
  if (confidence < 0.5) return 'text-destructive';
  if (confidence < 0.7) return 'text-yellow-600 dark:text-yellow-500';
  return 'text-green-600 dark:text-green-500';
}

export function BatchCorrectionPanel({
  document,
  onCorrectionComplete,
}: BatchCorrectionPanelProps) {
  const [corrections, setCorrections] = useState<FieldCorrection[]>([]);
  const [notes, setNotes] = useState('');
  const [activeFieldIndex, setActiveFieldIndex] = useState(0);
  const { toast } = useToast();
  const submitMutation = useSubmitBatchCorrections();

  // Initialize corrections when document changes
  useEffect(() => {
    if (document) {
      setCorrections(
        document.fields.map((field) => ({
          field,
          correctedValue: field.correctedValue || field.value,
          correctionType: (field.correctionType as CorrectionType) || 'general',
          isModified: false,
        }))
      );
      setNotes('');
      setActiveFieldIndex(0);
    } else {
      setCorrections([]);
    }
  }, [document]);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!document || corrections.length === 0) return;

      // Navigate between fields with Tab
      if (e.key === 'Tab' && !e.shiftKey) {
        e.preventDefault();
        setActiveFieldIndex((prev) =>
          prev < corrections.length - 1 ? prev + 1 : 0
        );
      } else if (e.key === 'Tab' && e.shiftKey) {
        e.preventDefault();
        setActiveFieldIndex((prev) =>
          prev > 0 ? prev - 1 : corrections.length - 1
        );
      }

      // Submit with Ctrl+Enter
      if (e.key === 'Enter' && e.ctrlKey) {
        e.preventDefault();
        handleSubmit();
      }

      // Reset with Ctrl+R
      if (e.key === 'r' && e.ctrlKey) {
        e.preventDefault();
        handleReset();
      }
    },
    [document, corrections]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const handleFieldChange = (index: number, value: string) => {
    setCorrections((prev) =>
      prev.map((c, i) =>
        i === index
          ? {
              ...c,
              correctedValue: value,
              isModified: value !== c.field.value,
            }
          : c
      )
    );
  };

  const handleTypeChange = (index: number, type: CorrectionType) => {
    setCorrections((prev) =>
      prev.map((c, i) => (i === index ? { ...c, correctionType: type } : c))
    );
  };

  const handleReset = () => {
    if (document) {
      setCorrections(
        document.fields.map((field) => ({
          field,
          correctedValue: field.value,
          correctionType: 'general',
          isModified: false,
        }))
      );
    }
  };

  const handleSubmit = async () => {
    if (!document) return;

    const modifiedCorrections = corrections.filter((c) => c.isModified);

    if (modifiedCorrections.length === 0) {
      toast({
        title: 'Keine Änderungen',
        description: 'Es wurden keine Felder geändert.',
        variant: 'default',
      });
      return;
    }

    const submissions: CorrectionSubmission[] = modifiedCorrections.map((c) => ({
      documentId: document.documentId,
      fieldName: c.field.fieldName,
      originalValue: c.field.value,
      correctedValue: c.correctedValue,
      correctionType: c.correctionType,
      backendUsed: document.backendUsed,
      notes: notes || undefined,
    }));

    try {
      const result = await submitMutation.mutateAsync(submissions);

      if (result.errors.length > 0) {
        toast({
          title: 'Teilweise erfolgreich',
          description: `${result.correctionIds.length} Korrekturen gespeichert, ${result.errors.length} Fehler.`,
          variant: 'default',
        });
      } else {
        toast({
          title: 'Korrekturen gespeichert',
          description: `${result.correctionIds.length} Felder korrigiert.`,
        });
      }

      onCorrectionComplete?.();
    } catch {
      toast({
        title: 'Fehler',
        description: 'Die Korrekturen konnten nicht gespeichert werden.',
        variant: 'destructive',
      });
    }
  };

  const modifiedCount = corrections.filter((c) => c.isModified).length;

  if (!document) {
    return (
      <Card className="h-full flex items-center justify-center">
        <div className="text-center p-8">
          <p className="text-sm text-muted-foreground">
            Wählen Sie ein Dokument aus der Queue aus.
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex-shrink-0 pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-sm font-medium">
              Felder korrigieren
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-1 truncate max-w-[300px]">
              {document.filename}
            </p>
          </div>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <Keyboard className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="left" className="max-w-xs">
                <div className="space-y-1 text-xs">
                  <p><kbd className="px-1 bg-muted rounded">Tab</kbd> Nächstes Feld</p>
                  <p><kbd className="px-1 bg-muted rounded">Shift+Tab</kbd> Vorheriges Feld</p>
                  <p><kbd className="px-1 bg-muted rounded">Ctrl+Enter</kbd> Speichern</p>
                  <p><kbd className="px-1 bg-muted rounded">Ctrl+R</kbd> Zurücksetzen</p>
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full">
          <div className="space-y-4 p-4">
            {corrections.map((correction, index) => (
              <div
                key={correction.field.fieldName}
                className={`p-3 rounded-lg border transition-colors ${
                  activeFieldIndex === index ? 'border-primary bg-accent/50' : ''
                }`}
                onClick={() => setActiveFieldIndex(index)}
              >
                <div className="flex items-center justify-between mb-2">
                  <Label className="text-sm font-medium">
                    {correction.field.fieldName}
                  </Label>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs font-medium ${getConfidenceColor(
                        correction.field.confidence
                      )}`}
                    >
                      {(correction.field.confidence * 100).toFixed(0)}%
                    </span>
                    {correction.isModified ? (
                      <Badge variant="default" className="text-xs">
                        Geändert
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-xs">
                        Original
                      </Badge>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="text-xs text-muted-foreground bg-muted p-2 rounded font-mono">
                    Original: {correction.field.value || '(leer)'}
                  </div>

                  <Input
                    value={correction.correctedValue}
                    onChange={(e) => handleFieldChange(index, e.target.value)}
                    placeholder="Korrigierter Wert"
                    className="text-sm"
                  />

                  <Select
                    value={correction.correctionType}
                    onValueChange={(value) =>
                      handleTypeChange(index, value as CorrectionType)
                    }
                  >
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(CORRECTION_TYPE_LABELS).map(([key, label]) => (
                        <SelectItem key={key} value={key}>
                          <div className="flex flex-col">
                            <span>{label}</span>
                            <span className="text-xs text-muted-foreground">
                              {CORRECTION_TYPE_DESCRIPTIONS[key as CorrectionType]}
                            </span>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            ))}

            <div className="space-y-2">
              <Label className="text-sm">Anmerkungen (optional)</Label>
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Zusätzliche Hinweise zur Korrektur..."
                className="text-sm resize-none"
                rows={2}
              />
            </div>
          </div>
        </ScrollArea>
      </CardContent>

      <CardFooter className="flex-shrink-0 border-t pt-4">
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2">
            {modifiedCount > 0 ? (
              <Badge variant="default" className="flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" />
                {modifiedCount} Änderung{modifiedCount > 1 ? 'en' : ''}
              </Badge>
            ) : (
              <Badge variant="secondary" className="flex items-center gap-1">
                <XCircle className="h-3 w-3" />
                Keine Änderungen
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleReset}
              disabled={submitMutation.isPending}
            >
              <RotateCcw className="h-4 w-4 mr-1" />
              Zurücksetzen
            </Button>
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={modifiedCount === 0 || submitMutation.isPending}
            >
              <Save className="h-4 w-4 mr-1" />
              {submitMutation.isPending ? 'Speichern...' : 'Speichern'}
            </Button>
          </div>
        </div>
      </CardFooter>
    </Card>
  );
}
