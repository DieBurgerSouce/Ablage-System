/**
 * Dashboard Settings Component
 *
 * Erweiterte Dashboard-Einstellungen
 */

import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
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
import { Save, Star, Copy, Trash2 } from 'lucide-react';
import {
  useDashboard,
  useUpdateDashboard,
  useSetFavorite,
  useDuplicateDashboard,
  useDeleteDashboard,
} from '../hooks/useDashboards';
import { useToast } from '@/components/ui/use-toast';

interface DashboardSettingsProps {
  dashboardId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function DashboardSettings({
  dashboardId,
  isOpen,
  onClose,
}: DashboardSettingsProps) {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { data: dashboard } = useDashboard(dashboardId);
  const updateMutation = useUpdateDashboard(dashboardId);
  const setFavoriteMutation = useSetFavorite(dashboardId);
  const duplicateMutation = useDuplicateDashboard();
  const deleteMutation = useDeleteDashboard();

  const [name, setName] = useState(dashboard?.name || '');
  const [description, setDescription] = useState(dashboard?.description || '');
  const [isFavorite, setIsFavorite] = useState(dashboard?.is_favorite || false);

  const handleSave = async () => {
    try {
      await updateMutation.mutateAsync({ name, description });

      if (isFavorite !== dashboard?.is_favorite) {
        await setFavoriteMutation.mutateAsync(isFavorite);
      }

      toast({
        title: 'Erfolgreich gespeichert',
        description: 'Dashboard-Einstellungen wurden aktualisiert',
      });
      onClose();
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Einstellungen konnten nicht gespeichert werden',
        variant: 'destructive',
      });
    }
  };

  const handleDuplicate = async () => {
    try {
      const newDashboard = await duplicateMutation.mutateAsync(dashboardId);
      toast({
        title: 'Dashboard dupliziert',
        description: 'Eine Kopie wurde erstellt',
      });
      navigate({ to: `/dashboards/${newDashboard.id}` });
      onClose();
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Dashboard konnte nicht dupliziert werden',
        variant: 'destructive',
      });
    }
  };

  const handleDelete = async () => {
    try {
      await deleteMutation.mutateAsync(dashboardId);
      toast({
        title: 'Dashboard gelöscht',
        description: 'Das Dashboard wurde permanent gelöscht',
      });
      navigate({ to: '/dashboards' });
      onClose();
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Dashboard konnte nicht gelöscht werden',
        variant: 'destructive',
      });
    }
  };

  if (!dashboard) return null;

  return (
    <>
      <Dialog open={isOpen} onOpenChange={onClose}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Dashboard-Einstellungen</DialogTitle>
            <DialogDescription>
              Verwalten Sie Ihr Dashboard
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Name */}
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Dashboard-Name"
              />
            </div>

            {/* Description */}
            <div className="space-y-2">
              <Label htmlFor="description">Beschreibung</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optionale Beschreibung"
                rows={3}
              />
            </div>

            {/* Favorite Toggle */}
            <div className="flex items-center justify-between p-3 rounded-lg border">
              <div className="flex items-center gap-3">
                <Star className="h-5 w-5 text-yellow-500" />
                <div>
                  <div className="font-medium text-sm">Favorit</div>
                  <div className="text-xs text-muted-foreground">
                    Als Favorit markieren
                  </div>
                </div>
              </div>
              <Switch checked={isFavorite} onCheckedChange={setIsFavorite} />
            </div>

            {/* Actions */}
            <div className="space-y-2 pt-4 border-t">
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={handleDuplicate}
                disabled={duplicateMutation.isPending}
              >
                <Copy className="h-4 w-4 mr-2" />
                Dashboard duplizieren
              </Button>

              <Button
                variant="outline"
                className="w-full justify-start text-destructive hover:text-destructive"
                onClick={() => setShowDeleteConfirm(true)}
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Dashboard löschen
              </Button>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              Abbrechen
            </Button>
            <Button onClick={handleSave} disabled={updateMutation.isPending}>
              <Save className="h-4 w-4 mr-2" />
              Speichern
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Dashboard löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Diese Aktion kann nicht rückgängig gemacht werden. Das Dashboard
              und alle enthaltenen Widgets werden permanent gelöscht.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Permanent löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
