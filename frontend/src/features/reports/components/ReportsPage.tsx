/**
 * ReportsPage Component
 *
 * Haupt-Seite fuer den Bereich "Berichte" mit drei Tabs:
 * - Meine Berichte: Gespeicherte Report-Templates
 * - Vorlagen: Vordefinierte Katalog-Templates
 * - Geplante Exporte: Scheduled Exports mit Cron, Format, Status
 */

import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  BarChart3,
  BookTemplate,
  Calendar,
  Clock,
  FileText,
  Loader2,
  Plus,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
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
import { ReportsList } from './ReportsList';
import { TemplateCatalog } from './TemplateCatalog';
import { ScheduledExportCard } from './ScheduledExportCard';
import {
  useScheduledExports,
  useToggleScheduledExport,
  useRunScheduledExportNow,
  useDeleteScheduledExport,
} from '../api/report-builder-api';
import type { ReportTemplate } from '../types';
import { ReportBuilder } from './ReportBuilder';

export function ReportsPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('berichte');
  const [builderOpen, setBuilderOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<ReportTemplate | undefined>();
  const [deleteExportId, setDeleteExportId] = useState<string | null>(null);

  // Scheduled Exports
  const { data: scheduledExports, isLoading: exportsLoading } = useScheduledExports();
  const toggleMutation = useToggleScheduledExport();
  const runNowMutation = useRunScheduledExportNow();
  const deleteMutation = useDeleteScheduledExport();

  const handleNewReport = () => {
    navigate({ to: '/berichte/builder' });
  };

  const handleEditReport = (template?: ReportTemplate) => {
    if (template) {
      setEditingTemplate(template);
      setBuilderOpen(true);
    } else {
      handleNewReport();
    }
  };

  const handleBuilderClose = () => {
    setBuilderOpen(false);
    setEditingTemplate(undefined);
  };

  const handleToggleExport = (exportId: string, active: boolean) => {
    toggleMutation.mutate({ exportId, active });
  };

  const handleRunExportNow = (exportId: string) => {
    runNowMutation.mutate(exportId);
  };

  const handleDeleteExport = (exportId: string) => {
    setDeleteExportId(exportId);
  };

  const confirmDeleteExport = () => {
    if (deleteExportId) {
      deleteMutation.mutate(deleteExportId);
      setDeleteExportId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BarChart3 className="h-7 w-7 text-primary" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Berichte</h1>
            <p className="text-sm text-muted-foreground">
              Reports erstellen, verwalten und automatisch ausfuehren.
            </p>
          </div>
        </div>
        <Button onClick={handleNewReport}>
          <Plus className="h-4 w-4 mr-2" />
          Neuer Bericht
        </Button>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="berichte" className="gap-2">
            <FileText className="h-4 w-4" />
            Meine Berichte
          </TabsTrigger>
          <TabsTrigger value="vorlagen" className="gap-2">
            <BookTemplate className="h-4 w-4" />
            Vorlagen
          </TabsTrigger>
          <TabsTrigger value="exporte" className="gap-2">
            <Calendar className="h-4 w-4" />
            Geplante Exporte
          </TabsTrigger>
        </TabsList>

        {/* Tab: Meine Berichte */}
        <TabsContent value="berichte" className="mt-6">
          <ReportsList onEdit={handleEditReport} onCreate={handleNewReport} />
        </TabsContent>

        {/* Tab: Vorlagen */}
        <TabsContent value="vorlagen" className="mt-6">
          <TemplateCatalog
            onTemplateCreated={(_templateId) => {
              setEditingTemplate(undefined);
              setBuilderOpen(false);
              // Template wurde erstellt, navigiere zur Builder-Ansicht
              navigate({ to: '/berichte' });
            }}
          />
        </TabsContent>

        {/* Tab: Geplante Exporte */}
        <TabsContent value="exporte" className="mt-6">
          {exportsLoading ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <Card key={i}>
                  <CardContent className="pt-6">
                    <div className="space-y-3">
                      <Skeleton className="h-5 w-3/4" />
                      <Skeleton className="h-4 w-1/2" />
                      <Skeleton className="h-16 w-full" />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : scheduledExports && scheduledExports.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {scheduledExports.map((exportItem) => (
                <ScheduledExportCard
                  key={exportItem.id}
                  exportItem={exportItem}
                  onToggle={handleToggleExport}
                  onRunNow={handleRunExportNow}
                  onDelete={handleDeleteExport}
                  isToggling={toggleMutation.isPending}
                  isRunning={runNowMutation.isPending}
                />
              ))}
            </div>
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Clock className="h-12 w-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-medium">Keine geplanten Exporte</h3>
                <p className="text-muted-foreground text-sm mt-1 text-center max-w-md">
                  Erstellen Sie einen Report und aktivieren Sie den Zeitplan,
                  um automatische Exporte einzurichten.
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Report Builder Sheet */}
      <ReportBuilder
        template={editingTemplate}
        open={builderOpen}
        onClose={handleBuilderClose}
      />

      {/* Delete Export Confirmation */}
      <AlertDialog
        open={!!deleteExportId}
        onOpenChange={(open) => !open && setDeleteExportId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Geplanten Export loeschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Der geplante Export wird dauerhaft geloescht. Zukuenftige
              automatische Ausfuehrungen werden gestoppt.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDeleteExport}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : null}
              Loeschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
