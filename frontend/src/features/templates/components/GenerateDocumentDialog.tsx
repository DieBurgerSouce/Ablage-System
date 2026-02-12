/**
 * GenerateDocumentDialog - Dialog zum Generieren eines Dokuments aus einer Vorlage
 *
 * Features:
 * - Dynamisches Formular basierend auf Template-Variablen
 * - Vorschau-Funktion
 * - Validierung
 * - Entity-Verknüpfung
 */

import { useState, useEffect } from 'react';
import DOMPurify from 'dompurify';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2, Eye, FileText, AlertCircle } from 'lucide-react';
import type { Template, GenerateDocumentRequest, TemplateVariable } from '../types/template-types';
import { VariableType, VARIABLE_TYPE_LABELS } from '../types/template-types';

interface GenerateDocumentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  template: Template | null;
  onSubmit: (data: GenerateDocumentRequest) => Promise<void>;
  onPreview?: (variables: Record<string, unknown>) => Promise<string>;
  isSubmitting?: boolean;
}

export function GenerateDocumentDialog({
  open,
  onOpenChange,
  template,
  onSubmit,
  onPreview,
  isSubmitting = false,
}: GenerateDocumentDialogProps) {
  const [activeTab, setActiveTab] = useState('variables');
  const [title, setTitle] = useState('');
  const [variables, setVariables] = useState<Record<string, unknown>>({});
  const [linkedEntityId, setLinkedEntityId] = useState('');
  const [saveToStorage, setSaveToStorage] = useState(true);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  // Reset form when dialog opens or template changes
  useEffect(() => {
    if (open && template) {
      setTitle(`${template.name} - ${new Date().toLocaleDateString('de-DE')}`);
      // Initialize variables with defaults
      const initialVars: Record<string, unknown> = {};
      template.variables?.forEach((v) => {
        if (v.default !== undefined) {
          initialVars[v.name] = v.default;
        } else {
          // Set default values based on type
          switch (v.type) {
            case VariableType.BOOLEAN:
              initialVars[v.name] = false;
              break;
            case VariableType.NUMBER:
            case VariableType.CURRENCY:
              initialVars[v.name] = 0;
              break;
            case VariableType.DATE:
              initialVars[v.name] = new Date().toISOString().split('T')[0];
              break;
            default:
              initialVars[v.name] = '';
          }
        }
      });
      setVariables(initialVars);
      setLinkedEntityId('');
      setSaveToStorage(true);
      setPreviewHtml(null);
      setErrors([]);
    }
    setActiveTab('variables');
  }, [open, template]);

  const handleVariableChange = (name: string, value: unknown) => {
    setVariables((prev) => ({ ...prev, [name]: value }));
    setPreviewHtml(null); // Clear preview when variables change
  };

  const handlePreview = async () => {
    if (!onPreview) return;

    setPreviewLoading(true);
    setErrors([]);
    try {
      const html = await onPreview(variables);
      setPreviewHtml(html);
      setActiveTab('preview');
    } catch (error) {
      setErrors([(error as Error).message || 'Vorschau konnte nicht generiert werden']);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors([]);

    // Validate required variables
    const missingRequired = template?.variables
      ?.filter((v) => v.required && !variables[v.name])
      .map((v) => v.label || v.name);

    if (missingRequired && missingRequired.length > 0) {
      setErrors([`Pflichtfelder fehlen: ${missingRequired.join(', ')}`]);
      return;
    }

    const data: GenerateDocumentRequest = {
      template_id: template!.id,
      title,
      variables,
      linked_entity_id: linkedEntityId || undefined,
      save_to_storage: saveToStorage,
    };

    await onSubmit(data);
  };

  const renderVariableInput = (variable: TemplateVariable) => {
    const value = variables[variable.name];

    switch (variable.type) {
      case VariableType.BOOLEAN:
        return (
          <div className="flex items-center gap-2">
            <Switch
              checked={value as boolean}
              onCheckedChange={(v) => handleVariableChange(variable.name, v)}
            />
            <span className="text-sm text-muted-foreground">
              {value ? 'Ja' : 'Nein'}
            </span>
          </div>
        );

      case VariableType.NUMBER:
        return (
          <Input
            type="number"
            value={value as number}
            onChange={(e) => handleVariableChange(variable.name, parseFloat(e.target.value) || 0)}
          />
        );

      case VariableType.CURRENCY:
        return (
          <div className="relative">
            <Input
              type="number"
              step="0.01"
              value={value as number}
              onChange={(e) => handleVariableChange(variable.name, parseFloat(e.target.value) || 0)}
              className="pr-8"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
              EUR
            </span>
          </div>
        );

      case VariableType.DATE:
        return (
          <Input
            type="date"
            value={value as string}
            onChange={(e) => handleVariableChange(variable.name, e.target.value)}
          />
        );

      case VariableType.DATETIME:
        return (
          <Input
            type="datetime-local"
            value={value as string}
            onChange={(e) => handleVariableChange(variable.name, e.target.value)}
          />
        );

      case VariableType.SELECT:
        return (
          <select
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
            value={value as string}
            onChange={(e) => handleVariableChange(variable.name, e.target.value)}
          >
            <option value="">Bitte wählen...</option>
            {variable.options?.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        );

      case VariableType.TEXT:
      default:
        // Check if it might be a multi-line field
        const isMultiLine =
          variable.name.includes('beschreibung') ||
          variable.name.includes('text') ||
          variable.name.includes('notiz');

        if (isMultiLine) {
          return (
            <Textarea
              value={value as string}
              onChange={(e) => handleVariableChange(variable.name, e.target.value)}
              rows={3}
            />
          );
        }

        return (
          <Input
            type="text"
            value={value as string}
            onChange={(e) => handleVariableChange(variable.name, e.target.value)}
          />
        );
    }
  };

  if (!template) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Dokument erstellen
            </DialogTitle>
            <DialogDescription>
              Erstellen Sie ein neues Dokument aus der Vorlage "{template.name}"
            </DialogDescription>
          </DialogHeader>

          {errors.length > 0 && (
            <Alert variant="destructive" className="mt-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                {errors.map((err, i) => (
                  <div key={i}>{err}</div>
                ))}
              </AlertDescription>
            </Alert>
          )}

          <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="variables">Variablen</TabsTrigger>
              <TabsTrigger value="options">Optionen</TabsTrigger>
              <TabsTrigger value="preview" disabled={!previewHtml}>
                Vorschau
              </TabsTrigger>
            </TabsList>

            {/* Variables Tab */}
            <TabsContent value="variables" className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label htmlFor="title">Dokumenttitel *</Label>
                <Input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Titel des generierten Dokuments"
                  required
                />
              </div>

              {template.variables && template.variables.length > 0 ? (
                <div className="space-y-4 border-t pt-4">
                  <h4 className="font-medium text-sm">Template-Variablen</h4>
                  {template.variables.map((variable) => (
                    <div key={variable.name} className="space-y-2">
                      <Label htmlFor={variable.name} className="flex items-center gap-1">
                        {variable.label || variable.name}
                        {variable.required && <span className="text-destructive">*</span>}
                        <span className="text-xs text-muted-foreground ml-2">
                          ({VARIABLE_TYPE_LABELS[variable.type]})
                        </span>
                      </Label>
                      {variable.description && (
                        <p className="text-xs text-muted-foreground">{variable.description}</p>
                      )}
                      {renderVariableInput(variable)}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-6 text-muted-foreground border rounded-md">
                  <p>Diese Vorlage hat keine definierten Variablen</p>
                </div>
              )}
            </TabsContent>

            {/* Options Tab */}
            <TabsContent value="options" className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label htmlFor="linkedEntity">Verknüpfter Geschäftspartner (optional)</Label>
                <Input
                  id="linkedEntity"
                  value={linkedEntityId}
                  onChange={(e) => setLinkedEntityId(e.target.value)}
                  placeholder="UUID des Geschäftspartners"
                />
                <p className="text-xs text-muted-foreground">
                  Verknüpft das generierte Dokument mit einem Kunden oder Lieferanten
                </p>
              </div>

              <div className="flex items-center justify-between border-t pt-4">
                <div className="space-y-0.5">
                  <Label>Im Speicher ablegen</Label>
                  <p className="text-sm text-muted-foreground">
                    Das generierte Dokument wird in MinIO gespeichert
                  </p>
                </div>
                <Switch checked={saveToStorage} onCheckedChange={setSaveToStorage} />
              </div>
            </TabsContent>

            {/* Preview Tab */}
            <TabsContent value="preview" className="mt-4">
              {previewHtml && (
                <div
                  className="border rounded-md p-4 bg-white min-h-[400px] max-h-[500px] overflow-auto"
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(previewHtml) }}
                />
              )}
            </TabsContent>
          </Tabs>

          <DialogFooter className="mt-6">
            {onPreview && (
              <Button
                type="button"
                variant="outline"
                onClick={handlePreview}
                disabled={previewLoading}
              >
                {previewLoading ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Eye className="h-4 w-4 mr-2" />
                )}
                Vorschau
              </Button>
            )}
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={isSubmitting || !title}>
              {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              <FileText className="h-4 w-4 mr-2" />
              Erstellen
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
