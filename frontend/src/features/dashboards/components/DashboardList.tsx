/**
 * Dashboard List Component
 *
 * Übersicht aller Dashboards (eigene, geteilte, Presets)
 */

import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { logger } from '@/lib/logger';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
import {
  LayoutDashboard,
  Plus,
  Star,
  Users,
  MoreVertical,
  Pencil,
  Copy,
  Trash2,
  Clock,
} from 'lucide-react';
import {
  useDashboards,
  useSharedDashboards,
  usePresets,
  useDeleteDashboard,
  useDuplicateDashboard,
  useSetFavorite,
  useCreateFromPreset,
} from '../hooks/useDashboards';
import type { Dashboard, DashboardPreset } from '../types';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';

export function DashboardList() {
  const navigate = useNavigate();
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const { data: dashboards = [], isLoading } = useDashboards();
  const { data: sharedDashboards = [] } = useSharedDashboards();
  const { data: presets = [] } = usePresets();

  const deleteMutation = useDeleteDashboard();
  const duplicateMutation = useDuplicateDashboard();
  const setFavoriteMutation = useSetFavorite(deleteId || '');
  const createFromPresetMutation = useCreateFromPreset();

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await deleteMutation.mutateAsync(deleteId);
      setDeleteId(null);
    } catch (error) {
      logger.error('Dashboard loeschen fehlgeschlagen', error);
    }
  };

  const handleDuplicate = async (id: string) => {
    try {
      const newDashboard = await duplicateMutation.mutateAsync(id);
      navigate({ to: `/dashboards/${newDashboard.id}` });
    } catch (error) {
      logger.error('Dashboard duplizieren fehlgeschlagen', error);
    }
  };

  const handleToggleFavorite = async (id: string, currentValue: boolean) => {
    try {
      await setFavoriteMutation.mutateAsync(!currentValue);
    } catch (error) {
      logger.error('Dashboard Favorit setzen fehlgeschlagen', error);
    }
  };

  const handleCreateFromPreset = async (presetId: string) => {
    try {
      const newDashboard = await createFromPresetMutation.mutateAsync(presetId);
      navigate({ to: `/dashboards/${newDashboard.id}` });
    } catch (error) {
      logger.error('Dashboard aus Vorlage erstellen fehlgeschlagen', error);
    }
  };

  const renderDashboardCard = (dashboard: Dashboard, canEdit = true) => (
    <Card
      key={dashboard.id}
      className="group hover:shadow-md transition-shadow cursor-pointer"
      onClick={() => navigate({ to: `/dashboards/${dashboard.id}` })}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <CardTitle className="text-lg">{dashboard.name}</CardTitle>
              {dashboard.is_favorite && (
                <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
              )}
              {dashboard.is_shared && (
                <Badge variant="secondary" className="gap-1">
                  <Users className="h-3 w-3" />
                  Geteilt
                </Badge>
              )}
            </div>
            {dashboard.description && (
              <CardDescription className="mt-1">
                {dashboard.description}
              </CardDescription>
            )}
          </div>
          {canEdit && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                <Button
                  variant="ghost"
                  size="icon"
                  className="opacity-0 group-hover:opacity-100"
                >
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate({ to: `/dashboards/${dashboard.id}/edit` });
                  }}
                >
                  <Pencil className="h-4 w-4 mr-2" />
                  Bearbeiten
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDuplicate(dashboard.id);
                  }}
                >
                  <Copy className="h-4 w-4 mr-2" />
                  Duplizieren
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
                    handleToggleFavorite(dashboard.id, dashboard.is_favorite);
                  }}
                >
                  <Star className="h-4 w-4 mr-2" />
                  {dashboard.is_favorite
                    ? 'Von Favoriten entfernen'
                    : 'Zu Favoriten'}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeleteId(dashboard.id);
                  }}
                  className="text-destructive"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Löschen
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{dashboard.widgets.length} Widgets</span>
          <div className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatDistanceToNow(new Date(dashboard.updated_at), {
              addSuffix: true,
              locale: de,
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );

  const renderPresetCard = (preset: DashboardPreset) => (
    <Card
      key={preset.id}
      className="group hover:shadow-md transition-shadow cursor-pointer"
      onClick={() => handleCreateFromPreset(preset.id)}
    >
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">{preset.name}</CardTitle>
        <CardDescription>{preset.description}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{preset.widgets.length} Widgets</span>
          <Badge variant="outline">{preset.role}</Badge>
        </div>
      </CardContent>
    </Card>
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Lade Dashboards...</div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <LayoutDashboard className="h-8 w-8" />
            Dashboards
          </h1>
          <p className="text-muted-foreground mt-1">
            Erstellen und verwalten Sie personalisierte Dashboards
          </p>
        </div>
        <Button
          onClick={() => navigate({ to: '/dashboards/new' })}
          className="gap-2"
        >
          <Plus className="h-4 w-4" />
          Neues Dashboard
        </Button>
      </div>

      <Tabs defaultValue="own" className="w-full">
        <TabsList className="grid w-full max-w-md grid-cols-3">
          <TabsTrigger value="own">Meine Dashboards</TabsTrigger>
          <TabsTrigger value="shared">
            Geteilt ({sharedDashboards.length})
          </TabsTrigger>
          <TabsTrigger value="presets">Vorlagen</TabsTrigger>
        </TabsList>

        <TabsContent value="own" className="mt-6">
          {dashboards.length === 0 ? (
            <Card className="p-12 text-center">
              <LayoutDashboard className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">
                Noch keine Dashboards
              </h3>
              <p className="text-muted-foreground mb-4">
                Erstellen Sie Ihr erstes Dashboard oder wählen Sie eine Vorlage
              </p>
              <Button
                onClick={() => navigate({ to: '/dashboards/new' })}
                className="gap-2"
              >
                <Plus className="h-4 w-4" />
                Neues Dashboard erstellen
              </Button>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {dashboards.map((dashboard) => renderDashboardCard(dashboard))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="shared" className="mt-6">
          {sharedDashboards.length === 0 ? (
            <Card className="p-12 text-center">
              <Users className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">
                Keine geteilten Dashboards
              </h3>
              <p className="text-muted-foreground">
                Dashboards, die mit Ihnen geteilt wurden, erscheinen hier
              </p>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {sharedDashboards.map((dashboard) =>
                renderDashboardCard(dashboard, dashboard.permission === 'edit')
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="presets" className="mt-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {presets.map((preset) => renderPresetCard(preset))}
          </div>
        </TabsContent>
      </Tabs>

      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Dashboard löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Diese Aktion kann nicht rückgängig gemacht werden. Das Dashboard
              wird permanent gelöscht.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
