/**
 * ValidationEditor
 *
 * Enterprise-Level Editor für Training-Sample-Validierung.
 * Split-View mit Dokument-Vorschau und Feld-Editor.
 */

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Check,
  X,
  ChevronLeft,
  RotateCcw,
  Save,
  AlertCircle,
  FileText,
  Languages,
  Table2,
  ChevronRight,
} from 'lucide-react';
import { Link } from '@tanstack/react-router';
import { ConfidenceIndicator } from './ConfidenceIndicator';
import { ApproveDialog } from './dialogs/ApproveDialog';
import { RejectDialog } from './dialogs/RejectDialog';
import {
  useTrainingSample,
  useUpdateTrainingSample,
  useVerifyTrainingSample,
} from '../hooks/use-validation-queries';
import { getSamplePreviewUrl, getSampleBenchmarks } from '../api/validation-api';
import { TrainingSampleStatus, SAMPLE_STATUS_LABELS, getStatusColor, getFieldConfidenceFromBenchmarks, type SampleBenchmark } from '../types';

interface ValidationEditorProps {
  sampleId: string;
}

interface EditableField {
  key: string;
  label: string;
  value: string;
  originalValue: string;
  confidence: number;
  isModified: boolean;
}

// Feld-Label auf Deutsch
const FIELD_LABELS: Record<string, string> = {
  invoice_number: 'Rechnungsnummer',
  date: 'Datum',
  total_amount: 'Gesamtbetrag',
  net_amount: 'Nettobetrag',
  vat_amount: 'MwSt-Betrag',
  vendor: 'Lieferant',
  vendor_name: 'Lieferantenname',
  customer: 'Kunde',
  customer_name: 'Kundenname',
  iban: 'IBAN',
  bic: 'BIC',
  vat_id: 'USt-IdNr',
  order_number: 'Bestellnummer',
  delivery_date: 'Lieferdatum',
  due_date: 'Fälligkeitsdatum',
  payment_terms: 'Zahlungsbedingungen',
};

export function ValidationEditor({ sampleId }: ValidationEditorProps) {
  // State
  const [fields, setFields] = useState<EditableField[]>([]);
  const [groundTruthText, setGroundTruthText] = useState('');
  const [annotationNotes, setAnnotationNotes] = useState('');
  const [previewPage, setPreviewPage] = useState(0);
  const [showApproveDialog, setShowApproveDialog] = useState(false);
  const [showRejectDialog, setShowRejectDialog] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Queries
  const { data: sample, isLoading, error } = useTrainingSample(sampleId);
  const updateMutation = useUpdateTrainingSample();
  const verifyMutation = useVerifyTrainingSample();

  // Benchmark-Daten für Konfidenz
  const [benchmarks, setBenchmarks] = useState<SampleBenchmark[]>([]);

  // Lade Benchmark-Daten wenn Sample verfügbar
  useEffect(() => {
    if (sample?.id) {
      getSampleBenchmarks(sample.id)
        .then(setBenchmarks)
        .catch(() => setBenchmarks([])); // Fallback bei Fehler
    }
  }, [sample?.id]);

  // Initialize fields from sample data with benchmark confidence
  useEffect(() => {
    if (sample) {
      const extractedFields = sample.extracted_fields || {};
      const initialFields: EditableField[] = Object.entries(extractedFields).map(
        ([key, value]) => ({
          key,
          label: FIELD_LABELS[key] || key,
          value: String(value ?? ''),
          originalValue: String(value ?? ''),
          confidence: getFieldConfidenceFromBenchmarks(benchmarks, key),
          isModified: false,
        })
      );
      setFields(initialFields);
      setGroundTruthText(sample.ground_truth_text || '');
      setAnnotationNotes(sample.annotation_notes || '');
      setHasChanges(false);
    }
  }, [sample, benchmarks]);

  // Handlers
  const handleFieldChange = (index: number, newValue: string) => {
    const newFields = [...fields];
    newFields[index] = {
      ...newFields[index],
      value: newValue,
      isModified: newValue !== newFields[index].originalValue,
    };
    setFields(newFields);
    setHasChanges(true);
  };

  const handleResetField = (index: number) => {
    const newFields = [...fields];
    newFields[index] = {
      ...newFields[index],
      value: newFields[index].originalValue,
      isModified: false,
    };
    setFields(newFields);
    // Check if any fields are still modified
    setHasChanges(newFields.some((f) => f.isModified) || groundTruthText !== sample?.ground_truth_text);
  };

  const handleResetAll = () => {
    if (sample) {
      const extractedFields = sample.extracted_fields || {};
      const resetFields: EditableField[] = Object.entries(extractedFields).map(
        ([key, value]) => ({
          key,
          label: FIELD_LABELS[key] || key,
          value: String(value ?? ''),
          originalValue: String(value ?? ''),
          confidence: getFieldConfidenceFromBenchmarks(benchmarks, key),
          isModified: false,
        })
      );
      setFields(resetFields);
      setGroundTruthText(sample.ground_truth_text || '');
      setAnnotationNotes(sample.annotation_notes || '');
      setHasChanges(false);
    }
  };

  const handleSave = async () => {
    if (!sample) return;

    // Build updated extracted_fields
    const updatedFields: Record<string, unknown> = {};
    fields.forEach((field) => {
      updatedFields[field.key] = field.value;
    });

    await updateMutation.mutateAsync({
      sampleId: sample.id,
      data: {
        extracted_fields: updatedFields,
        ground_truth_text: groundTruthText || undefined,
        annotation_notes: annotationNotes || undefined,
        status: TrainingSampleStatus.ANNOTATED,
      },
    });

    setHasChanges(false);
  };

  const handleApprove = async (notes?: string) => {
    if (!sample) return;
    await verifyMutation.mutateAsync({
      sampleId: sample.id,
      approved: true,
      notes,
    });
    setShowApproveDialog(false);
  };

  const handleReject = async (notes: string) => {
    if (!sample) return;
    await verifyMutation.mutateAsync({
      sampleId: sample.id,
      approved: false,
      notes,
    });
    setShowRejectDialog(false);
  };

  // Computed values
  const documentName = sample?.file_path?.split('/').pop() || 'Dokument';
  const previewUrl = sample ? getSamplePreviewUrl(sample.id, previewPage) : '';
  const isEditable =
    sample?.status === TrainingSampleStatus.PENDING ||
    sample?.status === TrainingSampleStatus.IN_PROGRESS;
  const canVerify =
    sample?.status === TrainingSampleStatus.ANNOTATED;
  const modifiedFieldsCount = fields.filter((f) => f.isModified).length;
  const lowConfidenceCount = fields.filter((f) => f.confidence < 0.8).length;

  // Loading state
  if (isLoading) {
    return (
      <div className="h-[calc(100vh-4rem)] flex flex-col">
        <div className="border-b bg-background p-4 flex items-center gap-4">
          <Skeleton className="w-8 h-8 rounded" />
          <div className="space-y-2">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-3 w-32" />
          </div>
        </div>
        <div className="flex-1 flex">
          <div className="w-1/2 p-4 flex items-center justify-center">
            <Skeleton className="w-64 h-96" />
          </div>
          <div className="w-1/2 p-6 space-y-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-10 w-full" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="h-[calc(100vh-4rem)] flex items-center justify-center">
        <Card className="w-96">
          <CardContent className="pt-6 text-center">
            <AlertCircle className="w-12 h-12 mx-auto text-destructive mb-4" />
            <h3 className="text-lg font-medium mb-2">Fehler beim Laden</h3>
            <p className="text-muted-foreground mb-4">{(error as Error).message}</p>
            <Button asChild variant="outline">
              <Link to="/validation-queue">Zurück zur Übersicht</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!sample) {
    return null;
  }

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      {/* Header */}
      <div className="border-b bg-background p-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/validation-queue">
              <ChevronLeft className="w-5 h-5" />
            </Link>
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">{documentName}</h2>
              <Badge variant={getStatusColor(sample.status)}>
                {SAMPLE_STATUS_LABELS[sample.status]}
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{sample.document_type || 'Unbekannt'}</span>
              <span>•</span>
              <span>{fields.length} Felder</span>
              {lowConfidenceCount > 0 && (
                <>
                  <span>•</span>
                  <span className="text-yellow-600">
                    {lowConfidenceCount} niedrige Konfidenz
                  </span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {hasChanges && (
            <Badge variant="outline" className="mr-2">
              {modifiedFieldsCount} Änderungen
            </Badge>
          )}
          <Button
            variant="outline"
            className="gap-2"
            onClick={handleResetAll}
            disabled={!hasChanges}
          >
            <RotateCcw className="w-4 h-4" />
            Zurücksetzen
          </Button>
          {isEditable && (
            <Button
              className="gap-2"
              onClick={handleSave}
              disabled={updateMutation.isPending}
            >
              <Save className="w-4 h-4" />
              {updateMutation.isPending ? 'Speichern...' : 'Speichern'}
            </Button>
          )}
          {canVerify && (
            <>
              <Button
                variant="destructive"
                className="gap-2"
                onClick={() => setShowRejectDialog(true)}
                disabled={verifyMutation.isPending}
              >
                <X className="w-4 h-4" />
                Ablehnen
              </Button>
              <Button
                className="gap-2 bg-green-600 hover:bg-green-700"
                onClick={() => setShowApproveDialog(true)}
                disabled={verifyMutation.isPending}
              >
                <Check className="w-4 h-4" />
                Verifizieren
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Main Content - Split View */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Document Viewer */}
        <div className="w-1/2 bg-muted/30 border-r flex flex-col">
          <div className="flex-1 p-4 flex items-center justify-center overflow-auto">
            {previewUrl ? (
              <img
                src={previewUrl}
                alt="Dokument-Vorschau"
                className="max-w-full max-h-full object-contain shadow-lg border bg-card"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = 'none';
                }}
              />
            ) : (
              <div className="text-center text-muted-foreground">
                <FileText className="w-16 h-16 mx-auto mb-4 opacity-50" />
                <p>Keine Vorschau verfügbar</p>
              </div>
            )}
          </div>
          {/* Page Navigation (for PDFs) */}
          <div className="border-t p-2 flex items-center justify-center gap-4 bg-background">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPreviewPage((p) => Math.max(0, p - 1))}
              disabled={previewPage === 0}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-sm text-muted-foreground">
              Seite {previewPage + 1}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPreviewPage((p) => p + 1)}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Right: Fields Editor */}
        <div className="w-1/2 overflow-y-auto p-6 bg-background">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>Extrahierte Daten</span>
                <div className="flex gap-1">
                  {sample.has_umlauts && (
                    <Badge variant="outline" className="text-xs gap-1">
                      <Languages className="w-3 h-3" />
                      Umlaute
                    </Badge>
                  )}
                  {sample.has_tables && (
                    <Badge variant="outline" className="text-xs gap-1">
                      <Table2 className="w-3 h-3" />
                      Tabellen
                    </Badge>
                  )}
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {fields.length === 0 ? (
                <p className="text-muted-foreground text-center py-4">
                  Keine extrahierten Felder vorhanden.
                </p>
              ) : (
                fields.map((field, index) => (
                  <div key={field.key} className="space-y-2">
                    <div className="flex justify-between items-center">
                      <Label htmlFor={field.key} className="flex items-center gap-2">
                        {field.label}
                        {field.isModified && (
                          <Badge variant="secondary" className="text-xs">
                            Geändert
                          </Badge>
                        )}
                      </Label>
                      <ConfidenceIndicator score={field.confidence} />
                    </div>
                    <div className="flex gap-2">
                      <Input
                        id={field.key}
                        value={field.value}
                        onChange={(e) => handleFieldChange(index, e.target.value)}
                        disabled={!isEditable}
                        className={
                          field.confidence < 0.8
                            ? 'border-yellow-500 bg-yellow-500/5'
                            : field.isModified
                            ? 'border-blue-500 bg-blue-500/5'
                            : ''
                        }
                      />
                      {field.isModified && isEditable && (
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => handleResetField(index)}
                          title="Originalwert wiederherstellen"
                        >
                          <RotateCcw className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))
              )}

              <Separator className="my-6" />

              {/* Ground Truth Text */}
              <div className="space-y-2">
                <Label htmlFor="ground_truth">Ground Truth Text</Label>
                <Textarea
                  id="ground_truth"
                  value={groundTruthText}
                  onChange={(e) => {
                    setGroundTruthText(e.target.value);
                    setHasChanges(true);
                  }}
                  disabled={!isEditable}
                  placeholder="Vollständiger korrekter Text des Dokuments..."
                  rows={6}
                />
              </div>

              {/* Annotation Notes */}
              <div className="space-y-2">
                <Label htmlFor="notes">Notizen zur Annotation</Label>
                <Textarea
                  id="notes"
                  value={annotationNotes}
                  onChange={(e) => {
                    setAnnotationNotes(e.target.value);
                    setHasChanges(true);
                  }}
                  disabled={!isEditable}
                  placeholder="Optionale Notizen zur Annotation..."
                  rows={3}
                />
              </div>

              <Separator className="my-6" />

              {lowConfidenceCount > 0 && (
                <div className="bg-yellow-50 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-200 p-4 rounded-md text-sm">
                  <p className="font-semibold mb-1">Hinweis</p>
                  <p>
                    Bitte überprüfen Sie besonders die gelb markierten Felder, da
                    hier die Erkennungsrate niedrig war.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Dialogs */}
      <ApproveDialog
        open={showApproveDialog}
        onOpenChange={setShowApproveDialog}
        onConfirm={handleApprove}
        isLoading={verifyMutation.isPending}
        documentName={documentName}
      />
      <RejectDialog
        open={showRejectDialog}
        onOpenChange={setShowRejectDialog}
        onConfirm={handleReject}
        isLoading={verifyMutation.isPending}
        documentName={documentName}
      />
    </div>
  );
}
