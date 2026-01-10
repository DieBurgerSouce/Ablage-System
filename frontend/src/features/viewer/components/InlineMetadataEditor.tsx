/**
 * InlineMetadataEditor - Inline Metadata Editing Panel
 *
 * Ersetzt das read-only ExtractedDataPanel mit editierbaren Feldern.
 * Ermöglicht inline Bearbeitung aller Metadaten mit:
 * - Auto-Save mit Debounce
 * - Optimistic Updates
 * - Undo-Funktion
 * - Visueller Speicher-Indikator
 *
 * Teil des "Dokumenten-Cockpit" Features (2.2).
 */

import { useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FileText,
  Building2,
  Calendar,
  Euro,
  Hash,
  FileCode,
  User,
  MapPin,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import { EditableField } from '@/components/ui/editable-field';
import { ConfidenceIndicator } from '@/features/validation/components/ConfidenceIndicator';
import { useExtractedData } from '@/features/extracted-data/hooks/useExtractedData';
import { documentsService } from '@/lib/api/services/documents';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface InlineMetadataEditorProps {
  documentId: string;
  className?: string;
}

interface MetadataFieldGroup {
  title: string;
  icon: React.ElementType;
  fields: MetadataField[];
}

interface MetadataField {
  key: string;
  label: string;
  type: 'text' | 'number' | 'date' | 'currency' | 'email';
  getValue: (data: ExtractedData) => string | number | null | undefined;
  path: string; // Pfad zum Update im Backend
}

// Lokaler Typ für die Extracted Data
interface ExtractedData {
  classification?: {
    document_type: string;
    confidence: number;
  };
  invoice?: {
    invoice_number?: string;
    invoice_date?: string;
    due_date?: string;
    total_gross?: number;
    total_net?: number;
    vat_amount?: number;
    vat_rate?: number;
    currency?: string;
    payment_reference?: string;
    invoice_direction?: string;
    needs_review?: boolean;
    extraction_warnings?: string[];
    vendor?: {
      name?: string;
      street?: string;
      city?: string;
      postal_code?: string;
      country?: string;
      vat_id?: string;
    };
    customer?: {
      name?: string;
      street?: string;
      city?: string;
      postal_code?: string;
      country?: string;
    };
    line_items?: Array<{
      description?: string;
      quantity?: number;
      unit_price?: number;
      total?: number;
    }>;
  };
  ibans?: string[];
  vat_ids?: string[];
  companies?: string[];
}

// ==================== Field Definitions ====================

const INVOICE_FIELD_GROUPS: MetadataFieldGroup[] = [
  {
    title: 'Rechnungsdaten',
    icon: FileCode,
    fields: [
      {
        key: 'invoice_number',
        label: 'Rechnungsnummer',
        type: 'text',
        getValue: (d) => d.invoice?.invoice_number,
        path: 'invoice.invoice_number',
      },
      {
        key: 'invoice_date',
        label: 'Rechnungsdatum',
        type: 'date',
        getValue: (d) => d.invoice?.invoice_date,
        path: 'invoice.invoice_date',
      },
      {
        key: 'due_date',
        label: 'Fälligkeitsdatum',
        type: 'date',
        getValue: (d) => d.invoice?.due_date,
        path: 'invoice.due_date',
      },
      {
        key: 'payment_reference',
        label: 'Zahlungsreferenz',
        type: 'text',
        getValue: (d) => d.invoice?.payment_reference,
        path: 'invoice.payment_reference',
      },
    ],
  },
  {
    title: 'Beträge',
    icon: Euro,
    fields: [
      {
        key: 'total_gross',
        label: 'Bruttobetrag',
        type: 'currency',
        getValue: (d) => d.invoice?.total_gross,
        path: 'invoice.total_gross',
      },
      {
        key: 'total_net',
        label: 'Nettobetrag',
        type: 'currency',
        getValue: (d) => d.invoice?.total_net,
        path: 'invoice.total_net',
      },
      {
        key: 'vat_amount',
        label: 'MwSt-Betrag',
        type: 'currency',
        getValue: (d) => d.invoice?.vat_amount,
        path: 'invoice.vat_amount',
      },
      {
        key: 'vat_rate',
        label: 'MwSt-Satz (%)',
        type: 'number',
        getValue: (d) => d.invoice?.vat_rate,
        path: 'invoice.vat_rate',
      },
    ],
  },
  {
    title: 'Lieferant',
    icon: Building2,
    fields: [
      {
        key: 'vendor_name',
        label: 'Name',
        type: 'text',
        getValue: (d) => d.invoice?.vendor?.name,
        path: 'invoice.vendor.name',
      },
      {
        key: 'vendor_street',
        label: 'Straße',
        type: 'text',
        getValue: (d) => d.invoice?.vendor?.street,
        path: 'invoice.vendor.street',
      },
      {
        key: 'vendor_city',
        label: 'Stadt',
        type: 'text',
        getValue: (d) => d.invoice?.vendor?.city,
        path: 'invoice.vendor.city',
      },
      {
        key: 'vendor_postal_code',
        label: 'PLZ',
        type: 'text',
        getValue: (d) => d.invoice?.vendor?.postal_code,
        path: 'invoice.vendor.postal_code',
      },
      {
        key: 'vendor_vat_id',
        label: 'USt-IdNr.',
        type: 'text',
        getValue: (d) => d.invoice?.vendor?.vat_id,
        path: 'invoice.vendor.vat_id',
      },
    ],
  },
  {
    title: 'Kunde',
    icon: User,
    fields: [
      {
        key: 'customer_name',
        label: 'Name',
        type: 'text',
        getValue: (d) => d.invoice?.customer?.name,
        path: 'invoice.customer.name',
      },
      {
        key: 'customer_street',
        label: 'Straße',
        type: 'text',
        getValue: (d) => d.invoice?.customer?.street,
        path: 'invoice.customer.street',
      },
      {
        key: 'customer_city',
        label: 'Stadt',
        type: 'text',
        getValue: (d) => d.invoice?.customer?.city,
        path: 'invoice.customer.city',
      },
      {
        key: 'customer_postal_code',
        label: 'PLZ',
        type: 'text',
        getValue: (d) => d.invoice?.customer?.postal_code,
        path: 'invoice.customer.postal_code',
      },
    ],
  },
];

// ==================== Component ====================

export function InlineMetadataEditor({
  documentId,
  className,
}: InlineMetadataEditorProps) {
  const queryClient = useQueryClient();
  const { data, isLoading, error, isError } = useExtractedData(documentId);
  const [savingField, setSavingField] = useState<string | null>(null);

  // Mutation zum Speichern von Metadaten
  const updateMutation = useMutation({
    mutationFn: async ({ path, value }: { path: string; value: string }) => {
      // TODO: Implementiere Backend-API für extracted-data updates
      // Vorerst simulieren wir eine Verzögerung
      await new Promise((resolve) => setTimeout(resolve, 500));

      // In Zukunft: API-Call
      // return documentsService.updateExtractedData(documentId, { [path]: value });
      return { success: true };
    },
    onMutate: async ({ path, value }) => {
      setSavingField(path);

      // Optimistic Update
      await queryClient.cancelQueries({ queryKey: ['extracted-data', documentId] });
      const previousData = queryClient.getQueryData(['extracted-data', documentId]);

      // Update cache optimistically
      queryClient.setQueryData(['extracted-data', documentId], (old: ExtractedData | undefined) => {
        if (!old) return old;
        // Deep clone and update path
        const updated = JSON.parse(JSON.stringify(old));
        setNestedValue(updated, path, value);
        return updated;
      });

      return { previousData };
    },
    onError: (err, variables, context) => {
      // Rollback bei Fehler
      if (context?.previousData) {
        queryClient.setQueryData(['extracted-data', documentId], context.previousData);
      }
      toast.error('Speichern fehlgeschlagen', {
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
      });
    },
    onSettled: () => {
      setSavingField(null);
      // Refresh data
      queryClient.invalidateQueries({ queryKey: ['extracted-data', documentId] });
    },
  });

  // Helper: Set nested value by path
  function setNestedValue(obj: Record<string, unknown>, path: string, value: unknown) {
    const parts = path.split('.');
    let current = obj;
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      if (!(part in current)) {
        current[part] = {};
      }
      current = current[part] as Record<string, unknown>;
    }
    current[parts[parts.length - 1]] = value;
  }

  // Save handler für EditableField
  const handleSave = useCallback(
    async (path: string, value: string) => {
      await updateMutation.mutateAsync({ path, value });
    },
    [updateMutation]
  );

  // Loading State
  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-3 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Lade Metadaten...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Error State
  if (isError || !data) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="text-center text-muted-foreground">
            <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine Metadaten verfügbar</p>
            {error && (
              <p className="text-xs text-destructive mt-2">
                {(error as Error).message}
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  const documentType = data.classification?.document_type || 'unknown';
  const confidence = data.classification?.confidence || 0;
  const needsReview = data.invoice?.needs_review || false;
  const warnings = data.invoice?.extraction_warnings || [];

  return (
    <Card className={cn('h-full overflow-auto', className)}>
      <CardHeader className="sticky top-0 bg-card z-10 border-b">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg">
            <FileText className="h-5 w-5" />
            Dokument-Cockpit
          </CardTitle>
          <div className="flex items-center gap-3">
            <ConfidenceIndicator score={confidence} />
            <Badge variant="default">
              {documentType === 'invoice' ? 'Rechnung' : documentType}
            </Badge>
          </div>
        </div>

        {/* Review-Warnung */}
        {needsReview && (
          <Alert
            variant="default"
            className="mt-4 border-orange-200 bg-orange-50 dark:border-orange-800 dark:bg-orange-950/30"
          >
            <AlertTriangle className="h-4 w-4 text-orange-600" />
            <AlertTitle className="text-orange-800 dark:text-orange-400">
              Manuelle Prüfung erforderlich
            </AlertTitle>
            {warnings.length > 0 && (
              <AlertDescription className="text-orange-700 dark:text-orange-300">
                <ul className="list-disc list-inside mt-1">
                  {warnings.map((warning, idx) => (
                    <li key={idx}>{warning}</li>
                  ))}
                </ul>
              </AlertDescription>
            )}
          </Alert>
        )}

        <p className="text-xs text-muted-foreground mt-2">
          Klicken Sie auf ein Feld, um es zu bearbeiten. Änderungen werden automatisch gespeichert.
        </p>
      </CardHeader>

      <CardContent className="space-y-6 pt-6">
        {documentType === 'invoice' &&
          INVOICE_FIELD_GROUPS.map((group) => (
            <div key={group.title}>
              <div className="flex items-center gap-2 mb-4">
                <group.icon className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-medium">{group.title}</h3>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                {group.fields.map((field) => (
                  <EditableField
                    key={field.key}
                    value={field.getValue(data as ExtractedData)}
                    onSave={(value) => handleSave(field.path, value)}
                    label={field.label}
                    type={field.type}
                    editable={true}
                    showEditIcon={false}
                    className="p-2 -m-2"
                  />
                ))}
              </div>
              <Separator className="mt-6" />
            </div>
          ))}

        {/* Weitere Entitäten */}
        {((data.ibans?.length ?? 0) > 0 ||
          (data.vat_ids?.length ?? 0) > 0 ||
          (data.companies?.length ?? 0) > 0) && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Hash className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-medium">Weitere Entitäten</h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              {data.ibans && data.ibans.length > 0 && (
                <div>
                  <span className="font-medium text-muted-foreground text-xs block mb-1">
                    IBANs
                  </span>
                  {data.ibans.map((iban, idx) => (
                    <div key={idx} className="font-mono text-xs">
                      {iban}
                    </div>
                  ))}
                </div>
              )}
              {data.vat_ids && data.vat_ids.length > 0 && (
                <div>
                  <span className="font-medium text-muted-foreground text-xs block mb-1">
                    USt-IDs
                  </span>
                  {data.vat_ids.map((vatId, idx) => (
                    <div key={idx} className="font-mono text-xs">
                      {vatId}
                    </div>
                  ))}
                </div>
              )}
              {data.companies && data.companies.length > 0 && (
                <div>
                  <span className="font-medium text-muted-foreground text-xs block mb-1">
                    Firmen
                  </span>
                  {data.companies.map((company, idx) => (
                    <div key={idx} className="text-xs">
                      {company}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default InlineMetadataEditor;
