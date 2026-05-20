/**
 * CorrectionFeedbackForm Component
 * Form for users to correct extracted values
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { RefreshCw, Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
  useConfidences,
  useLearnFromCorrections,
} from '../hooks/use-ki-pipeline-queries';
import { FIELD_LABELS } from '../types/ki-pipeline-types';
import type { CorrectionInput } from '../types/ki-pipeline-types';

interface CorrectionFeedbackFormProps {
  documentId: string;
  className?: string;
  onSuccess?: () => void;
}

export function CorrectionFeedbackForm({
  documentId,
  className,
  onSuccess,
}: CorrectionFeedbackFormProps) {
  const { data: fields, isLoading } = useConfidences(documentId);
  const learnMutation = useLearnFromCorrections();

  const [corrections, setCorrections] = useState<
    Record<string, string | number>
  >({});
  const [modifiedFields, setModifiedFields] = useState<Set<string>>(new Set());

  const handleFieldChange = (field: string, value: string) => {
    setCorrections((prev) => ({ ...prev, [field]: value }));
    setModifiedFields((prev) => new Set(prev).add(field));
  };

  const handleSubmit = async () => {
    if (modifiedFields.size === 0) {
      toast.error('Keine Änderungen vorgenommen');
      return;
    }

    const correctionList: CorrectionInput[] = Array.from(modifiedFields)
      .filter((field) => {
        const originalField = fields?.find((f) => f.field === field);
        return originalField && corrections[field] !== undefined;
      })
      .map((field) => {
        const originalField = fields!.find((f) => f.field === field);
        return {
          field,
          original_value: originalField!.extracted_value,
          corrected_value: corrections[field],
        };
      });

    if (correctionList.length === 0) {
      toast.error('Keine gültigen Korrekturen gefunden');
      return;
    }

    await learnMutation.mutateAsync(
      {
        document_id: documentId,
        corrections: correctionList,
      },
      {
        onSuccess: () => {
          setModifiedFields(new Set());
          setCorrections({});
          onSuccess?.();
        },
      }
    );
  };

  const handleReset = () => {
    setCorrections({});
    setModifiedFields(new Set());
    toast.info('Änderungen zurückgesetzt');
  };

  if (isLoading) {
    return (
      <Card className={cn('w-full', className)}>
        <CardContent className="py-8 text-center text-muted-foreground">
          Lade Extraktionsdaten...
        </CardContent>
      </Card>
    );
  }

  if (!fields || fields.length === 0) {
    return (
      <Card className={cn('w-full', className)}>
        <CardContent className="py-8 text-center text-muted-foreground">
          Keine Extraktionsdaten verfügbar
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn('w-full', className)}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Korrekturen einreichen
          </CardTitle>
          {modifiedFields.size > 0 && (
            <Badge variant="secondary">
              {modifiedFields.size} Änderung(en)
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-4">
          {fields.map((field) => {
            const isModified = modifiedFields.has(field.field);
            const fieldLabel = FIELD_LABELS[field.field] || field.field;
            const currentValue =
              corrections[field.field] !== undefined
                ? corrections[field.field]
                : field.extracted_value ?? '';

            return (
              <div key={field.field} className="space-y-2">
                <Label htmlFor={`field-${field.field}`} className="text-sm">
                  {fieldLabel}
                  {isModified && (
                    <Badge variant="outline" className="ml-2 text-xs">
                      Geändert
                    </Badge>
                  )}
                </Label>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <span className="text-xs text-muted-foreground">
                      Extrahiert
                    </span>
                    <Input
                      value={
                        field.extracted_value !== null &&
                        field.extracted_value !== undefined
                          ? String(field.extracted_value)
                          : ''
                      }
                      disabled
                      className="bg-muted"
                    />
                  </div>
                  <div className="space-y-1">
                    <span className="text-xs text-muted-foreground">
                      Korrektur
                    </span>
                    <Input
                      id={`field-${field.field}`}
                      value={String(currentValue)}
                      onChange={(e) =>
                        handleFieldChange(field.field, e.target.value)
                      }
                      placeholder="Korrigierten Wert eingeben"
                      className={cn(
                        isModified && 'border-primary ring-1 ring-primary'
                      )}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <Separator />

        <div className="flex items-center gap-3">
          <Button
            onClick={handleSubmit}
            disabled={modifiedFields.size === 0 || learnMutation.isPending}
            className="flex-1"
          >
            <Check className="h-4 w-4 mr-2" />
            {learnMutation.isPending
              ? 'Wird gespeichert...'
              : `${modifiedFields.size} Korrektur(en) einreichen`}
          </Button>
          <Button
            variant="outline"
            onClick={handleReset}
            disabled={modifiedFields.size === 0 || learnMutation.isPending}
          >
            <X className="h-4 w-4 mr-2" />
            Zurücksetzen
          </Button>
        </div>

        <p className="text-xs text-muted-foreground">
          Hinweis: Ihre Korrekturen werden verwendet, um das KI-Modell zu
          verbessern und die Genauigkeit zukünftiger Extraktionen zu erhöhen.
        </p>
      </CardContent>
    </Card>
  );
}
