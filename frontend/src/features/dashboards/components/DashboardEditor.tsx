/**
 * Dashboard Editor Component
 *
 * Dashboard-Editor mit Drag & Drop Grid-Layout
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Responsive, WidthProvider, type Layout } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
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
import { Save, X, Plus, Settings2, Trash2, Share2 } from 'lucide-react';
import {
  useDashboard,
  useUpdateDashboard,
  useAddWidget,
  useDeleteWidget,
  useSaveLayout,
} from '../hooks/useDashboards';
import { WidgetPalette } from './WidgetPalette';
import { ShareDashboardDialog } from './ShareDashboardDialog';
import {
  DocumentCountWidget,
  InvoiceSummaryWidget,
  CashflowChartWidget,
  RecentDocumentsWidget,
  RiskOverviewWidget,
  WorkflowStatusWidget,
} from './widgets';
import type { Widget, WidgetType } from '../types';
import { useToast } from '@/components/ui/use-toast';

const ResponsiveGridLayout = WidthProvider(Responsive);

interface DashboardEditorProps {
  dashboardId: string;
}

export function DashboardEditor({ dashboardId }: DashboardEditorProps) {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [isEditing, setIsEditing] = useState(true);
  const [showPalette, setShowPalette] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [showShareDialog, setShowShareDialog] = useState(false);
  const [deleteWidgetId, setDeleteWidgetId] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  const { data: dashboard, isLoading } = useDashboard(dashboardId);
  const updateDashboard = useUpdateDashboard(dashboardId);
  const addWidget = useAddWidget(dashboardId);
  const deleteWidget = useDeleteWidget(dashboardId);
  const saveLayout = useSaveLayout(dashboardId);

  // Initialize form values
  useEffect(() => {
    if (dashboard) {
      setName(dashboard.name);
      setDescription(dashboard.description || '');
    }
  }, [dashboard]);

  const handleSaveMetadata = async () => {
    try {
      await updateDashboard.mutateAsync({ name, description });
      toast({
        title: 'Erfolgreich gespeichert',
        description: 'Dashboard-Einstellungen wurden aktualisiert',
      });
      setShowSettings(false);
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Dashboard-Einstellungen konnten nicht gespeichert werden',
        variant: 'destructive',
      });
    }
  };

  const handleAddWidget = async (type: WidgetType, title: string) => {
    try {
      await addWidget.mutateAsync({
        type,
        title,
        config: {},
        x: 0,
        y: Infinity, // Will be placed at the bottom
        w: 4,
        h: 2,
      });
      toast({
        title: 'Widget hinzugefügt',
        description: `${title} wurde zum Dashboard hinzugefügt`,
      });
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Widget konnte nicht hinzugefügt werden',
        variant: 'destructive',
      });
    }
  };

  const handleDeleteWidget = async () => {
    if (!deleteWidgetId) return;
    try {
      await deleteWidget.mutateAsync(deleteWidgetId);
      toast({
        title: 'Widget entfernt',
        description: 'Das Widget wurde vom Dashboard entfernt',
      });
      setDeleteWidgetId(null);
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Widget konnte nicht entfernt werden',
        variant: 'destructive',
      });
    }
  };

  const handleLayoutChange = useCallback(
    (layout: Layout[]) => {
      if (!dashboard || !isEditing) return;

      const widgets = layout.map((item) => ({
        id: item.i,
        x: item.x,
        y: item.y,
        w: item.w,
        h: item.h,
      }));

      // Debounced save
      const timeoutId = setTimeout(() => {
        saveLayout.mutate({ widgets });
      }, 1000);

      return () => clearTimeout(timeoutId);
    },
    [dashboard, isEditing, saveLayout]
  );

  const layouts = useMemo(() => {
    if (!dashboard) return { lg: [], md: [], sm: [] };

    const lg = dashboard.widgets.map((widget) => ({
      i: widget.id,
      x: widget.x,
      y: widget.y,
      w: widget.w,
      h: widget.h,
      minW: 2,
      minH: 2,
    }));

    return { lg, md: lg, sm: lg };
  }, [dashboard]);

  const renderWidget = (widget: Widget) => {
    const commonProps = {
      widget,
      onRemove: () => setDeleteWidgetId(widget.id),
      isEditing,
    };

    switch (widget.type) {
      case 'document_count':
        return <DocumentCountWidget {...commonProps} />;
      case 'invoice_summary':
        return <InvoiceSummaryWidget {...commonProps} />;
      case 'cashflow_chart':
        return <CashflowChartWidget {...commonProps} />;
      case 'recent_documents':
        return <RecentDocumentsWidget {...commonProps} />;
      case 'risk_overview':
        return <RiskOverviewWidget {...commonProps} />;
      case 'workflow_status':
        return <WorkflowStatusWidget {...commonProps} />;
      default:
        return (
          <div className="p-4 text-sm text-muted-foreground">
            Unbekannter Widget-Typ: {widget.type}
          </div>
        );
    }
  };

  if (isLoading || !dashboard) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-muted-foreground">Lädt Dashboard...</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <div className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate({ to: '/dashboards' })}
            >
              <X className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="text-xl font-semibold">{dashboard.name}</h1>
              {dashboard.description && (
                <p className="text-sm text-muted-foreground">
                  {dashboard.description}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowPalette(!showPalette)}
            >
              <Plus className="h-4 w-4 mr-2" />
              Widgets
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowShareDialog(true)}
            >
              <Share2 className="h-4 w-4 mr-2" />
              Teilen
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowSettings(true)}
            >
              <Settings2 className="h-4 w-4 mr-2" />
              Einstellungen
            </Button>
            <Button
              onClick={() => setIsEditing(!isEditing)}
              variant={isEditing ? 'default' : 'outline'}
              size="sm"
            >
              <Save className="h-4 w-4 mr-2" />
              {isEditing ? 'Bearbeiten beenden' : 'Bearbeiten'}
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Dashboard Grid */}
        <div className="flex-1 overflow-auto p-6">
          {dashboard.widgets.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <div className="max-w-md">
                <h3 className="text-lg font-semibold mb-2">
                  Noch keine Widgets
                </h3>
                <p className="text-muted-foreground mb-4">
                  Fügen Sie Widgets hinzu, um Ihr Dashboard zu personalisieren
                </p>
                <Button onClick={() => setShowPalette(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  Widget hinzufügen
                </Button>
              </div>
            </div>
          ) : (
            <ResponsiveGridLayout
              className="layout"
              layouts={layouts}
              breakpoints={{ lg: 1200, md: 996, sm: 768 }}
              cols={{ lg: 12, md: 8, sm: 4 }}
              rowHeight={80}
              isDraggable={isEditing}
              isResizable={isEditing}
              onLayoutChange={handleLayoutChange}
              draggableHandle=".drag-handle"
            >
              {dashboard.widgets.map((widget) => (
                <div key={widget.id} className="drag-handle">
                  {renderWidget(widget)}
                </div>
              ))}
            </ResponsiveGridLayout>
          )}
        </div>

        {/* Widget Palette Sidebar */}
        {showPalette && (
          <div className="w-80 border-l bg-muted/10">
            <WidgetPalette onAddWidget={handleAddWidget} isOpen={showPalette} />
          </div>
        )}
      </div>

      {/* Settings Sheet */}
      <Sheet open={showSettings} onOpenChange={setShowSettings}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Dashboard-Einstellungen</SheetTitle>
            <SheetDescription>
              Passen Sie Name und Beschreibung des Dashboards an
            </SheetDescription>
          </SheetHeader>
          <div className="space-y-4 mt-6">
            <div>
              <label className="text-sm font-medium mb-2 block">Name</label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Dashboard-Name"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">
                Beschreibung
              </label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optionale Beschreibung"
                rows={3}
              />
            </div>
            <Button onClick={handleSaveMetadata} className="w-full">
              <Save className="h-4 w-4 mr-2" />
              Speichern
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      {/* Share Dialog */}
      {showShareDialog && (
        <ShareDashboardDialog
          dashboardId={dashboardId}
          isOpen={showShareDialog}
          onClose={() => setShowShareDialog(false)}
        />
      )}

      {/* Delete Widget Confirmation */}
      <AlertDialog
        open={!!deleteWidgetId}
        onOpenChange={() => setDeleteWidgetId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Widget entfernen?</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie dieses Widget wirklich vom Dashboard entfernen?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteWidget}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Entfernen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
