/**
 * TemplatesPage - Hauptseite fuer Dokumenten-Vorlagen
 *
 * Features:
 * - Vorlagen-Uebersicht mit Tabelle
 * - Kategorie-Statistiken
 * - Filter und Suche
 * - CRUD-Operationen
 * - Dokumentengenerierung
 */

import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { Plus, FileText, RefreshCw } from 'lucide-react';
import {
  useTemplates,
  useCategorySummary,
  useCreateTemplate,
  useUpdateTemplate,
  useDeleteTemplate,
  useGenerateDocument,
  usePreviewTemplate,
} from '../api/templates-api';
import { TemplateTable } from '../components/TemplateTable';
import { TemplateFilters } from '../components/TemplateFilters';
import { CategoryStatsCards } from '../components/CategoryStatsCards';
import { TemplateFormDialog } from '../components/TemplateFormDialog';
import { TemplateDetailSheet } from '../components/TemplateDetailSheet';
import { GenerateDocumentDialog } from '../components/GenerateDocumentDialog';
import type {
  Template,
  TemplateListParams,
  TemplateCreateRequest,
  TemplateUpdateRequest,
  GenerateDocumentRequest,
} from '../types/template-types';
import { TemplateCategory } from '../types/template-types';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

export function TemplatesPage() {
  const { toast } = useToast();

  // Filter state
  const [filters, setFilters] = useState<TemplateListParams>({
    offset: 0,
    limit: 50,
  });

  // Dialog states
  const [formDialogOpen, setFormDialogOpen] = useState(false);
  const [detailSheetOpen, setDetailSheetOpen] = useState(false);
  const [generateDialogOpen, setGenerateDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);

  // Queries
  const {
    data: templatesData,
    isLoading: templatesLoading,
    refetch: refetchTemplates,
  } = useTemplates(filters);
  const { data: categories, isLoading: categoriesLoading } = useCategorySummary();

  // Mutations
  const createTemplate = useCreateTemplate();
  const updateTemplate = useUpdateTemplate();
  const deleteTemplate = useDeleteTemplate();
  const generateDocument = useGenerateDocument();
  const previewTemplate = usePreviewTemplate();

  // Handlers
  const handleCategoryClick = useCallback((category: TemplateCategory) => {
    setFilters((prev) => ({
      ...prev,
      category: prev.category === category ? undefined : category,
      offset: 0,
    }));
  }, []);

  const handleView = useCallback((template: Template) => {
    setSelectedTemplate(template);
    setDetailSheetOpen(true);
  }, []);

  const handleEdit = useCallback((template: Template) => {
    setSelectedTemplate(template);
    setFormDialogOpen(true);
  }, []);

  const handleDelete = useCallback((template: Template) => {
    setSelectedTemplate(template);
    setDeleteDialogOpen(true);
  }, []);

  const handleGenerate = useCallback((template: Template) => {
    setSelectedTemplate(template);
    setGenerateDialogOpen(true);
  }, []);

  const handleDuplicate = useCallback(
    async (template: Template) => {
      const duplicateData: TemplateCreateRequest = {
        name: `${template.name} (Kopie)`,
        code: `${template.code}-COPY-${Date.now()}`.substring(0, 50),
        description: template.description,
        category: template.category,
        content: template.content,
        header_content: template.header_content,
        footer_content: template.footer_content,
        css_styles: template.css_styles,
        page_size: template.page_size,
        orientation: template.orientation,
        margins: template.margins,
        output_format: template.output_format,
        variables: template.variables,
        tags: template.tags,
        is_default: false,
      };

      try {
        await createTemplate.mutateAsync(duplicateData);
        toast({
          title: 'Vorlage dupliziert',
          description: 'Die Vorlage wurde erfolgreich kopiert.',
        });
      } catch (error) {
        toast({
          title: 'Fehler',
          description: 'Die Vorlage konnte nicht dupliziert werden.',
          variant: 'destructive',
        });
      }
    },
    [createTemplate, toast]
  );

  const handleSetDefault = useCallback(
    async (template: Template) => {
      try {
        await updateTemplate.mutateAsync({
          id: template.id,
          data: { is_default: !template.is_default },
        });
        toast({
          title: template.is_default ? 'Standard entfernt' : 'Als Standard gesetzt',
          description: template.is_default
            ? 'Die Vorlage ist nicht mehr Standard.'
            : 'Diese Vorlage ist jetzt die Standard-Vorlage fuer die Kategorie.',
        });
      } catch (error) {
        toast({
          title: 'Fehler',
          description: 'Der Status konnte nicht geaendert werden.',
          variant: 'destructive',
        });
      }
    },
    [updateTemplate, toast]
  );

  const handleCreateOrUpdate = useCallback(
    async (data: TemplateCreateRequest | TemplateUpdateRequest) => {
      try {
        if (selectedTemplate) {
          await updateTemplate.mutateAsync({ id: selectedTemplate.id, data });
          toast({
            title: 'Vorlage aktualisiert',
            description: 'Die Aenderungen wurden gespeichert.',
          });
        } else {
          await createTemplate.mutateAsync(data as TemplateCreateRequest);
          toast({
            title: 'Vorlage erstellt',
            description: 'Die neue Vorlage wurde erstellt.',
          });
        }
        setFormDialogOpen(false);
        setSelectedTemplate(null);
      } catch (error) {
        toast({
          title: 'Fehler',
          description: 'Die Vorlage konnte nicht gespeichert werden.',
          variant: 'destructive',
        });
      }
    },
    [selectedTemplate, createTemplate, updateTemplate, toast]
  );

  const handleConfirmDelete = useCallback(async () => {
    if (!selectedTemplate) return;

    try {
      await deleteTemplate.mutateAsync(selectedTemplate.id);
      toast({
        title: 'Vorlage geloescht',
        description: 'Die Vorlage wurde erfolgreich geloescht.',
      });
      setDeleteDialogOpen(false);
      setSelectedTemplate(null);
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Die Vorlage konnte nicht geloescht werden.',
        variant: 'destructive',
      });
    }
  }, [selectedTemplate, deleteTemplate, toast]);

  const handleGenerateDocument = useCallback(
    async (data: GenerateDocumentRequest) => {
      try {
        const result = await generateDocument.mutateAsync(data);
        toast({
          title: 'Dokument erstellt',
          description: `"${result.title}" wurde erfolgreich generiert.`,
        });
        setGenerateDialogOpen(false);
        setSelectedTemplate(null);
      } catch (error) {
        toast({
          title: 'Fehler',
          description: 'Das Dokument konnte nicht erstellt werden.',
          variant: 'destructive',
        });
      }
    },
    [generateDocument, toast]
  );

  const handlePreview = useCallback(
    async (variables: Record<string, unknown>) => {
      if (!selectedTemplate) throw new Error('Keine Vorlage ausgewaehlt');
      return previewTemplate.mutateAsync({ id: selectedTemplate.id, data: { variables } });
    },
    [selectedTemplate, previewTemplate]
  );

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <FileText className="h-8 w-8" />
            Dokumentvorlagen
          </h1>
          <p className="text-muted-foreground mt-1">
            Verwalten Sie Ihre Dokumentvorlagen und erstellen Sie Dokumente mit einem Klick
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetchTemplates()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Aktualisieren
          </Button>
          <Button
            onClick={() => {
              setSelectedTemplate(null);
              setFormDialogOpen(true);
            }}
          >
            <Plus className="h-4 w-4 mr-2" />
            Neue Vorlage
          </Button>
        </div>
      </div>

      {/* Category Stats */}
      <CategoryStatsCards
        categories={categories || []}
        isLoading={categoriesLoading}
        selectedCategory={filters.category}
        onCategoryClick={handleCategoryClick}
      />

      {/* Filters */}
      <TemplateFilters filters={filters} onFiltersChange={setFilters} />

      {/* Table */}
      <TemplateTable
        templates={templatesData?.items || []}
        isLoading={templatesLoading}
        onView={handleView}
        onEdit={handleEdit}
        onDelete={handleDelete}
        onGenerate={handleGenerate}
        onDuplicate={handleDuplicate}
        onSetDefault={handleSetDefault}
      />

      {/* Pagination Info */}
      {templatesData && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Zeige {templatesData.items.length} von {templatesData.total} Vorlagen
          </span>
          {templatesData.total > templatesData.limit && (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={filters.offset === 0}
                onClick={() =>
                  setFilters((prev) => ({
                    ...prev,
                    offset: Math.max(0, (prev.offset || 0) - (prev.limit || 50)),
                  }))
                }
              >
                Zurueck
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={(filters.offset || 0) + (filters.limit || 50) >= templatesData.total}
                onClick={() =>
                  setFilters((prev) => ({
                    ...prev,
                    offset: (prev.offset || 0) + (prev.limit || 50),
                  }))
                }
              >
                Weiter
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Dialogs */}
      <TemplateFormDialog
        open={formDialogOpen}
        onOpenChange={(open) => {
          setFormDialogOpen(open);
          if (!open) setSelectedTemplate(null);
        }}
        template={selectedTemplate}
        onSubmit={handleCreateOrUpdate}
        isSubmitting={createTemplate.isPending || updateTemplate.isPending}
      />

      <TemplateDetailSheet
        open={detailSheetOpen}
        onOpenChange={(open) => {
          setDetailSheetOpen(open);
          if (!open) setSelectedTemplate(null);
        }}
        template={selectedTemplate}
        onEdit={(template) => {
          setDetailSheetOpen(false);
          setSelectedTemplate(template);
          setFormDialogOpen(true);
        }}
        onGenerate={(template) => {
          setDetailSheetOpen(false);
          setSelectedTemplate(template);
          setGenerateDialogOpen(true);
        }}
      />

      <GenerateDocumentDialog
        open={generateDialogOpen}
        onOpenChange={(open) => {
          setGenerateDialogOpen(open);
          if (!open) setSelectedTemplate(null);
        }}
        template={selectedTemplate}
        onSubmit={handleGenerateDocument}
        onPreview={handlePreview}
        isSubmitting={generateDocument.isPending}
      />

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Vorlage loeschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Moechten Sie die Vorlage "{selectedTemplate?.name}" wirklich loeschen? Diese Aktion
              kann nicht rueckgaengig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Loeschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
