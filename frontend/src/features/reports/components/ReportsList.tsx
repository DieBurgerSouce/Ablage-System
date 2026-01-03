/**
 * ReportsList Component
 *
 * Zeigt eine Liste aller Report-Templates mit Aktionen.
 */

import { useState } from 'react';
import {
  BarChart3,
  Calendar,
  Clock,
  Copy,
  FileText,
  MoreVertical,
  Pencil,
  Play,
  Plus,
  Share2,
  Trash2,
  Users,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
import { Skeleton } from '@/components/ui/skeleton';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  useTemplates,
  useDeleteTemplate,
  useCloneTemplate,
  useExecuteReport,
} from '../hooks/useReports';
import type { ReportTemplate, ReportType, DataSource } from '../types';

interface ReportsListProps {
  // TYPE SAFETY FIX: Optional template fuer "create new" vs "edit existing"
  onEdit?: (template?: ReportTemplate) => void;
  onCreate?: () => void;
  onShare?: (template: ReportTemplate) => void;
  onSchedule?: (template: ReportTemplate) => void;
}

const reportTypeLabels: Record<ReportType, string> = {
  document: 'Dokumente',
  finance: 'Finanzen',
  ocr: 'OCR-Qualitaet',
  custom: 'Benutzerdefiniert',
};

const dataSourceLabels: Record<DataSource, string> = {
  documents: 'Dokumente',
  invoices: 'Rechnungen',
  entities: 'Entitaeten',
  ocr_results: 'OCR-Ergebnisse',
};

const reportTypeColors: Record<ReportType, string> = {
  document: 'bg-blue-500/10 text-blue-500',
  finance: 'bg-green-500/10 text-green-500',
  ocr: 'bg-purple-500/10 text-purple-500',
  custom: 'bg-orange-500/10 text-orange-500',
};

export function ReportsList({ onEdit, onCreate, onShare, onSchedule }: ReportsListProps) {
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [templateToDelete, setTemplateToDelete] = useState<ReportTemplate | null>(null);

  const { data: templates, isLoading } = useTemplates();
  const deleteMutation = useDeleteTemplate();
  const cloneMutation = useCloneTemplate();
  const executeMutation = useExecuteReport();

  const handleDelete = (template: ReportTemplate) => {
    setTemplateToDelete(template);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = () => {
    if (templateToDelete) {
      deleteMutation.mutate(templateToDelete.id);
      setDeleteDialogOpen(false);
      setTemplateToDelete(null);
    }
  };

  const handleClone = (template: ReportTemplate) => {
    cloneMutation.mutate({
      templateId: template.id,
      newName: `${template.name} (Kopie)`,
    });
  };

  const handleExecute = (template: ReportTemplate) => {
    executeMutation.mutate({ templateId: template.id });
  };

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-20" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!templates || templates.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <FileText className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium">Keine Reports vorhanden</h3>
          <p className="text-muted-foreground text-sm mt-1">
            Erstellen Sie Ihren ersten Report-Template.
          </p>
          {/* TYPE SAFETY FIX: Separate onCreate Callback statt unsafe Cast */}
          <Button className="mt-4" onClick={() => onCreate?.() ?? onEdit?.()}>
            <Plus className="h-4 w-4 mr-2" />
            Neuer Report
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {templates.map((template) => (
          <Card key={template.id} className="hover:shadow-md transition-shadow">
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <CardTitle className="text-base truncate">{template.name}</CardTitle>
                  {template.description && (
                    <CardDescription className="line-clamp-2 mt-1">
                      {template.description}
                    </CardDescription>
                  )}
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8">
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => handleExecute(template)}>
                      <Play className="h-4 w-4 mr-2" />
                      Ausfuehren
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => onEdit?.(template)}>
                      <Pencil className="h-4 w-4 mr-2" />
                      Bearbeiten
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => handleClone(template)}>
                      <Copy className="h-4 w-4 mr-2" />
                      Duplizieren
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => onShare?.(template)}>
                      <Share2 className="h-4 w-4 mr-2" />
                      Teilen
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => onSchedule?.(template)}>
                      <Calendar className="h-4 w-4 mr-2" />
                      Zeitplan
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => handleDelete(template)}
                      className="text-destructive focus:text-destructive"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Loeschen
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2 mb-3">
                <Badge variant="secondary" className={reportTypeColors[template.report_type]}>
                  {reportTypeLabels[template.report_type]}
                </Badge>
                <Badge variant="outline">{dataSourceLabels[template.data_source]}</Badge>
                {template.is_public && (
                  <Badge variant="outline" className="gap-1">
                    <Users className="h-3 w-3" />
                    Oeffentlich
                  </Badge>
                )}
                {template.is_scheduled && (
                  <Badge variant="outline" className="gap-1 bg-green-500/10 text-green-600">
                    <Clock className="h-3 w-3" />
                    Geplant
                  </Badge>
                )}
              </div>

              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <BarChart3 className="h-3 w-3" />
                  {template.columns?.length || 0} Spalten
                </span>
                {template.last_executed_at && (
                  <span>
                    Zuletzt:{' '}
                    {formatDistanceToNow(new Date(template.last_executed_at), {
                      addSuffix: true,
                      locale: de,
                    })}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Report-Template loeschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Moechten Sie das Template &quot;{templateToDelete?.name}&quot; wirklich loeschen?
              Diese Aktion kann nicht rueckgaengig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Loeschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
