/**
 * ExtractionConfidencePanel Component
 * Full panel showing all extracted fields with confidence
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Brain, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ConfidenceFieldDisplay } from './ConfidenceFieldDisplay';
import { useConfidences } from '../hooks/use-ki-pipeline-queries';
import { getConfidenceLevel } from '../types/ki-pipeline-types';

interface ExtractionConfidencePanelProps {
  documentId: string;
  className?: string;
}

// Field grouping by section
const FIELD_SECTIONS = {
  Kopfdaten: [
    'document_number',
    'document_date',
    'supplier_name',
    'customer_name',
    'delivery_date',
    'order_number',
  ],
  Positionen: [
    'position_number',
    'article_number',
    'description',
    'quantity',
    'unit_price',
    'line_total',
  ],
  Summen: ['total_net', 'tax_amount', 'tax_rate', 'total_gross'],
  Zahlungsbedingungen: [
    'payment_terms',
    'due_date',
    'bank_account',
    'iban',
    'bic',
  ],
};

export function ExtractionConfidencePanel({
  documentId,
  className,
}: ExtractionConfidencePanelProps) {
  const { data: fields, isLoading, error } = useConfidences(documentId);

  if (isLoading) {
    return (
      <Card className={cn('w-full', className)}>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent className="space-y-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={cn('w-full', className)}>
        <CardContent className="py-8 text-center text-muted-foreground">
          Fehler beim Laden der Konfidenzwerte
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

  // Calculate overall confidence
  const overallConfidence =
    fields.reduce((sum, f) => sum + f.confidence, 0) / fields.length;
  const overallLevel = getConfidenceLevel(overallConfidence);
  const overallPercent = Math.round(overallConfidence * 100);

  // Group fields by section
  const groupedFields: Record<string, typeof fields> = {};
  Object.entries(FIELD_SECTIONS).forEach(([section, fieldNames]) => {
    const sectionFields = fields.filter((f) => fieldNames.includes(f.field));
    if (sectionFields.length > 0) {
      groupedFields[section] = sectionFields;
    }
  });

  // Any remaining fields go to "Weitere"
  const usedFields = new Set(
    Object.values(FIELD_SECTIONS).flat()
  );
  const remainingFields = fields.filter((f) => !usedFields.has(f.field));
  if (remainingFields.length > 0) {
    groupedFields['Weitere'] = remainingFields;
  }

  return (
    <Card className={cn('w-full', className)}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            Extraktions-Konfidenz
          </CardTitle>
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-muted-foreground" />
            <Badge
              variant={overallLevel.color === 'green' ? 'default' : 'secondary'}
              className={cn(
                'text-base',
                overallLevel.color === 'yellow' && 'bg-yellow-500 text-white',
                overallLevel.color === 'red' && 'bg-red-500 text-white'
              )}
            >
              {overallPercent}% Gesamt
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {Object.entries(groupedFields).map(([section, sectionFields], idx) => (
          <div key={section}>
            {idx > 0 && <Separator className="my-4" />}
            <h3 className="text-sm font-semibold text-muted-foreground mb-3">
              {section}
            </h3>
            <div className="space-y-4">
              {sectionFields.map((field) => (
                <ConfidenceFieldDisplay key={field.field} field={field} />
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
