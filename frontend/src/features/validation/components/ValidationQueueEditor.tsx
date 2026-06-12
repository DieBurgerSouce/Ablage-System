/**
 * ValidationQueueEditor
 *
 * Enterprise-Grade Side-by-Side Editor für die Validierung.
 * Links: PDF-Viewer mit Bounding-Box Highlighting
 * Rechts: Field Editor mit Validierung
 *
 * Features:
 * - Echtes PDF-Rendering mit react-pdf/pdfjs-dist (ValidationPDFViewer)
 * - Bounding Box Highlighting beim Hover mit Confidence-Farben
 * - Bidirektionale Interaktion: Klick auf Box -> Scroll zu Feld
 * - Multi-Page Navigation mit Seitenzahlanzeige
 * - Zoom-Support (50% - 300%)
 * - Inline Field Editing
 * - Umlaut und Format Validierung
 * - Keyboard Shortcuts (Ctrl+Enter: Genehmigen, Ctrl+Shift+R: Ablehnen, Esc: Abbrechen)
 * - Authenticated Preview Loading via API
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  ArrowLeft,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  FileText,
  Edit3,
  Check,
  X,
  Loader2,
} from 'lucide-react';
import { ValidationPDFViewer } from './ValidationPDFViewer';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { toast } from 'sonner';
import {
  useQueueItem,
  useQueueItemFields,
  useUpdateField,
  useValidateField,
  useValidateAllFields,
  useApproveQueueItem,
  useRejectQueueItem,
} from '../hooks/use-validation-queue';
import {
  ValidationStatus,
  VALIDATION_STATUS_LABELS,
  getValidationStatusColor,
  getConfidenceColor,
  getConfidenceBgColor,
} from '../types/validation-queue.types';
import type { ValidationFieldReview, RejectionCategory } from '../types/validation-queue.types';
import { RejectReasonDialog } from './RejectReasonDialog';

interface ValidationQueueEditorProps {
  itemId: string;
}

export function ValidationQueueEditor({ itemId }: ValidationQueueEditorProps) {
  const navigate = useNavigate();

  // State
  const [editingFieldId, setEditingFieldId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [highlightedField, setHighlightedField] = useState<string | null>(null);
  const [pdfZoom, setPdfZoom] = useState(1);
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfNumPages, setPdfNumPages] = useState<number | null>(null);
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);

  // Queries
  const { data: item, isLoading: isLoadingItem, error: itemError } = useQueueItem(itemId);
  const { data: fields, isLoading: isLoadingFields } = useQueueItemFields(itemId);

  // Mutations
  const updateField = useUpdateField();
  const validateField = useValidateField();
  const validateAllFields = useValidateAllFields();
  const approveItem = useApproveQueueItem();
  const rejectItem = useRejectQueueItem();

  // Refs
  const fieldRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Handlers - FIX Phase 7.8: useCallback für stabile Referenzen in useEffect
  const handleBack = useCallback(() => {
    navigate({ to: '/validation-queue' });
  }, [navigate]);

  const handleApprove = useCallback(async () => {
    try {
      await approveItem.mutateAsync({ itemId, data: { apply_corrections: true } });
      toast.success('Dokument genehmigt');
      navigate({ to: '/validation-queue' });
    } catch {
      toast.error('Fehler beim Genehmigen');
    }
  }, [approveItem, itemId, navigate]);

  // Keyboard Shortcuts - FIX Phase 7.8: Korrekte Dependencies (handleApprove als Callback)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl+Enter: Genehmigen
      if (e.ctrlKey && e.key === 'Enter' && item?.status === ValidationStatus.PENDING) {
        e.preventDefault();
        handleApprove();
      }
      // Ctrl+Shift+R: Ablehnen
      if (e.ctrlKey && e.shiftKey && e.key === 'R' && item?.status === ValidationStatus.PENDING) {
        e.preventDefault();
        setRejectDialogOpen(true);
      }
      // Escape: Editing abbrechen
      if (e.key === 'Escape' && editingFieldId) {
        setEditingFieldId(null);
        setEditValue('');
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [item?.status, editingFieldId, handleApprove]);

  const handleRejectClick = () => {
    setRejectDialogOpen(true);
  };

  const handleRejectConfirm = async (reason: string, category?: RejectionCategory) => {
    try {
      await rejectItem.mutateAsync({
        itemId,
        data: { reason, rejection_category: category },
      });
      toast.success('Dokument abgelehnt');
      setRejectDialogOpen(false);
      navigate({ to: '/validation-queue' });
    } catch {
      toast.error('Fehler beim Ablehnen');
    }
  };

  const handleStartEdit = (field: ValidationFieldReview) => {
    setEditingFieldId(field.id);
    setEditValue(field.corrected_value || field.original_value || '');
  };

  const handleSaveEdit = async () => {
    if (!editingFieldId) return;

    try {
      await updateField.mutateAsync({
        itemId,
        fieldId: editingFieldId,
        data: { corrected_value: editValue },
      });
      setEditingFieldId(null);
      setEditValue('');
      toast.success('Feld aktualisiert');
    } catch (error) {
      toast.error('Fehler beim Speichern');
    }
  };

  const handleCancelEdit = () => {
    setEditingFieldId(null);
    setEditValue('');
  };

  const handleValidateField = async (fieldId: string) => {
    try {
      const result = await validateField.mutateAsync({ itemId, fieldId });
      if (!result.is_valid) {
        toast.warning(`Validierungsfehler: ${result.errors.length} Problem(e) gefunden`);
      } else {
        toast.success('Feld validiert');
      }
    } catch (error) {
      toast.error('Fehler bei der Validierung');
    }
  };

  const handleValidateAll = async () => {
    try {
      await validateAllFields.mutateAsync(itemId);
    } catch (error) {
      toast.error('Fehler bei der Validierung');
    }
  };

  const handleFieldHover = (fieldKey: string | null) => {
    setHighlightedField(fieldKey);
  };

  // PDF Field Click Handler - scrollt zum entsprechenden Feld
  const handlePdfFieldClick = useCallback((fieldKey: string) => {
    setHighlightedField(fieldKey);
    const fieldElement = fieldRefs.current[fieldKey];
    if (fieldElement) {
      fieldElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, []);

  // PDF Num Pages Handler
  const handleNumPagesChange = useCallback((numPages: number) => {
    setPdfNumPages(numPages);
  }, []);

  // Loading State
  if (isLoadingItem) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin mx-auto mb-4 text-primary" />
          <p className="text-muted-foreground">Lade Dokument...</p>
        </div>
      </div>
    );
  }

  // Error State
  if (itemError || !item) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md">
          <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-destructive" />
          <h2 className="text-xl font-semibold mb-2">Fehler beim Laden</h2>
          <p className="text-muted-foreground mb-4">
            {itemError ? (itemError as Error).message : 'Dokument nicht gefunden'}
          </p>
          <Button onClick={handleBack}>Zurück zur Übersicht</Button>
        </div>
      </div>
    );
  }

  const isPending = item.status === ValidationStatus.PENDING;
  const isInProgress = item.status === ValidationStatus.IN_PROGRESS;
  const canEdit = isPending || isInProgress;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b bg-background">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={handleBack} aria-label="Zurück zur Übersicht">
            <ArrowLeft className="w-5 h-5" aria-hidden="true" />
          </Button>
          <div>
            <h1 className="text-lg font-bold tracking-tight">
              {item.document_name || `Dokument ${item.document_id.slice(0, 8)}`}
            </h1>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>{item.document_type || 'Unbekannter Typ'}</span>
              <span>·</span>
              <Badge variant={getValidationStatusColor(item.status)}>
                {VALIDATION_STATUS_LABELS[item.status]}
              </Badge>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {canEdit && (
            <>
              <Button
                variant="outline"
                onClick={handleValidateAll}
                disabled={validateAllFields.isPending}
                aria-label="Alle Felder validieren"
              >
                <RefreshCw
                  className={`w-4 h-4 mr-2 ${validateAllFields.isPending ? 'animate-spin' : ''}`}
                  aria-hidden="true"
                />
                Alle validieren
              </Button>
              <Button
                variant="destructive"
                onClick={handleRejectClick}
                disabled={rejectItem.isPending}
                aria-label="Dokument ablehnen"
              >
                <XCircle className="w-4 h-4 mr-2" aria-hidden="true" />
                Ablehnen
              </Button>
              <Button
                onClick={handleApprove}
                disabled={approveItem.isPending}
                aria-label="Dokument genehmigen"
              >
                <CheckCircle className="w-4 h-4 mr-2" aria-hidden="true" />
                Genehmigen
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Main Content - Side by Side */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: PDF Viewer */}
        <div className="w-1/2 border-r flex flex-col bg-muted/30">
          {/* PDF Controls */}
          <div className="flex items-center justify-between px-4 py-2 border-b bg-background">
            <div className="flex items-center gap-2" role="group" aria-label="PDF-Seitennavigation">
              <Button
                variant="outline"
                size="icon"
                onClick={() => setPdfPage((p) => Math.max(1, p - 1))}
                disabled={pdfPage <= 1}
                aria-label="Vorherige Seite"
              >
                <ChevronLeft className="w-4 h-4" aria-hidden="true" />
              </Button>
              <span className="text-sm min-w-[100px] text-center" aria-live="polite">
                Seite {pdfPage}{pdfNumPages ? ` / ${pdfNumPages}` : ''}
              </span>
              <Button
                variant="outline"
                size="icon"
                onClick={() => setPdfPage((p) => (pdfNumPages ? Math.min(pdfNumPages, p + 1) : p + 1))}
                disabled={pdfNumPages !== null && pdfPage >= pdfNumPages}
                aria-label="Nächste Seite"
              >
                <ChevronRight className="w-4 h-4" aria-hidden="true" />
              </Button>
            </div>
            <div className="flex items-center gap-2" role="group" aria-label="PDF-Zoom">
              <Button
                variant="outline"
                size="icon"
                onClick={() => setPdfZoom((z) => Math.max(0.5, z - 0.1))}
                disabled={pdfZoom <= 0.5}
                aria-label="Verkleinern"
              >
                <ZoomOut className="w-4 h-4" aria-hidden="true" />
              </Button>
              <span className="text-sm min-w-[60px] text-center" aria-live="polite">
                {Math.round(pdfZoom * 100)}%
              </span>
              <Button
                variant="outline"
                size="icon"
                onClick={() => setPdfZoom((z) => Math.min(3, z + 0.1))}
                disabled={pdfZoom >= 3}
                aria-label="Vergrößern"
              >
                <ZoomIn className="w-4 h-4" aria-hidden="true" />
              </Button>
            </div>
          </div>

          {/* PDF Content - Echtes PDF-Rendering mit pdfjs-dist */}
          <div className="flex-1 overflow-hidden">
            <ValidationPDFViewer
              documentId={item.document_id}
              fields={fields || []}
              highlightedFieldKey={highlightedField}
              onFieldClick={handlePdfFieldClick}
              zoom={pdfZoom}
              currentPage={pdfPage}
              onPageChange={setPdfPage}
              onNumPagesChange={handleNumPagesChange}
            />
          </div>
        </div>

        {/* Right: Field Editor */}
        <div className="w-1/2 flex flex-col">
          <div className="px-4 py-3 border-b bg-background">
            <h2 className="font-semibold">Extrahierte Felder</h2>
            <p className="text-sm text-muted-foreground">
              {fields?.length || 0} Felder · {item.fields_below_threshold} unter Schwellenwert
            </p>
          </div>

          <ScrollArea className="flex-1">
            <div className="p-4 space-y-3">
              {isLoadingFields ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-20 w-full" />
                ))
              ) : fields && fields.length > 0 ? (
                fields.map((field) => (
                  <Card
                    key={field.id}
                    ref={(el) => (fieldRefs.current[field.field_key] = el)}
                    className={`transition-all ${
                      highlightedField === field.field_key
                        ? 'ring-2 ring-primary'
                        : field.is_below_threshold
                          ? 'border-yellow-500/50'
                          : ''
                    }`}
                    onMouseEnter={() => handleFieldHover(field.field_key)}
                    onMouseLeave={() => handleFieldHover(null)}
                  >
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-2">
                            <Label className="text-sm font-medium">
                              {field.field_label}
                            </Label>
                            {field.confidence_score !== null && (
                              <Badge
                                variant="outline"
                                className={`text-xs ${getConfidenceColor(field.confidence_score)} ${getConfidenceBgColor(field.confidence_score)}`}
                              >
                                {Math.round(field.confidence_score * 100)}%
                              </Badge>
                            )}
                            {field.is_below_threshold && (
                              <AlertTriangle className="w-4 h-4 text-yellow-500" />
                            )}
                            {field.was_corrected && (
                              <Badge variant="secondary" className="text-xs">
                                Korrigiert
                              </Badge>
                            )}
                          </div>

                          {editingFieldId === field.id ? (
                            <div className="flex items-center gap-2">
                              <Input
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                className="flex-1"
                                autoFocus
                                aria-label={`${field.field_label} bearbeiten`}
                                aria-describedby={
                                  field.validation_errors && field.validation_errors.length > 0
                                    ? `field-error-${field.id}`
                                    : undefined
                                }
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    handleSaveEdit();
                                  }
                                  if (e.key === 'Escape') {
                                    handleCancelEdit();
                                  }
                                }}
                              />
                              <Button
                                size="icon"
                                onClick={handleSaveEdit}
                                disabled={updateField.isPending}
                                aria-label="Änderung speichern"
                              >
                                <Check className="w-4 h-4" aria-hidden="true" />
                              </Button>
                              <Button
                                size="icon"
                                variant="outline"
                                onClick={handleCancelEdit}
                                aria-label="Bearbeitung abbrechen"
                              >
                                <X className="w-4 h-4" aria-hidden="true" />
                              </Button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <div
                                className="flex-1 p-2 bg-muted rounded text-sm font-mono"
                                aria-label={`${field.field_label}: ${field.corrected_value || field.original_value || 'Kein Wert'}`}
                              >
                                {field.corrected_value || field.original_value || '-'}
                              </div>
                              {canEdit && (
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  onClick={() => handleStartEdit(field)}
                                  aria-label={`${field.field_label} bearbeiten`}
                                >
                                  <Edit3 className="w-4 h-4" aria-hidden="true" />
                                </Button>
                              )}
                            </div>
                          )}

                          {/* Validation Errors */}
                          {field.validation_errors && field.validation_errors.length > 0 && (
                            <div
                              id={`field-error-${field.id}`}
                              className="mt-2 text-xs text-destructive"
                              role="alert"
                              aria-live="assertive"
                            >
                              {field.validation_errors.map((error, i) => (
                                <div key={i} className="flex items-center gap-1">
                                  <AlertTriangle className="w-3 h-3" aria-hidden="true" />
                                  <span>{error.message || error.type}</span>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Umlaut Issues */}
                          {field.umlaut_issues && field.umlaut_issues.length > 0 && (
                            <div className="mt-2 text-xs text-yellow-600">
                              {field.umlaut_issues.map((issue, i) => (
                                <div key={i} className="flex items-center gap-1">
                                  <span>Umlaut: {issue.original} → {issue.suggested}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        {canEdit && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleValidateField(field.id)}
                            disabled={validateField.isPending}
                            aria-label={`${field.field_label} validieren`}
                          >
                            Validieren
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p>Keine Felder gefunden</p>
                </div>
              )}
            </div>
          </ScrollArea>

          {/* Field Stats Footer */}
          <div className="px-4 py-3 border-t bg-muted/30 text-sm text-muted-foreground">
            <div className="flex items-center justify-between">
              <span>
                Durchschn. Konfidenz:{' '}
                {item.avg_field_confidence !== null
                  ? `${Math.round(item.avg_field_confidence * 100)}%`
                  : '-'}
              </span>
              <span>
                Korrekturen: {item.corrections_made}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Keyboard Shortcuts Hint */}
      <div
        className="px-6 py-2 border-t bg-muted/30 text-xs text-muted-foreground"
        role="note"
        aria-label="Verfügbare Tastaturkürzel"
      >
        {/* Screen Reader: Vollständige Beschreibung der Shortcuts */}
        <span className="sr-only">
          Tastaturkürzel: Strg plus Enter zum Genehmigen des Dokuments.
          Strg plus Umschalt plus R zum Ablehnen des Dokuments.
          Escape zum Abbrechen der Feldbearbeitung.
        </span>
        {/* Visuelle Darstellung */}
        <span className="mr-4" aria-hidden="true">
          <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">Ctrl+Enter</kbd> Genehmigen
        </span>
        <span className="mr-4" aria-hidden="true">
          <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">Ctrl+Shift+R</kbd> Ablehnen
        </span>
        <span aria-hidden="true">
          <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">Esc</kbd> Bearbeitung abbrechen
        </span>
      </div>

      {/* Reject Dialog */}
      <RejectReasonDialog
        open={rejectDialogOpen}
        onOpenChange={setRejectDialogOpen}
        onConfirm={handleRejectConfirm}
        isLoading={rejectItem.isPending}
        documentName={item?.document_name}
      />
    </div>
  );
}

export default ValidationQueueEditor;
