/**
 * DeleteSpaceDialog - Bestätigungsdialog zum Löschen eines Bereichs
 */

import * as React from 'react';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { AlertTriangle, Loader2 } from 'lucide-react';
import type { PrivatSpaceWithStats } from '@/types/privat';

interface DeleteSpaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  space: PrivatSpaceWithStats | null;
  onConfirm: (spaceId: string) => Promise<void>;
  isLoading?: boolean;
}

export function DeleteSpaceDialog({
  open,
  onOpenChange,
  space,
  onConfirm,
  isLoading = false,
}: DeleteSpaceDialogProps) {
  const [confirmText, setConfirmText] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);

  const isConfirmValid = confirmText === space?.name;

  const handleConfirm = async () => {
    if (!space || !isConfirmValid) return;

    setError(null);
    try {
      await onConfirm(space.id);
      setConfirmText('');
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Löschen');
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      setConfirmText('');
      setError(null);
    }
    onOpenChange(newOpen);
  };

  if (!space) return null;

  const hasContent = space.documentCount > 0 || space.folderCount > 0;

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-full bg-destructive/10">
              <AlertTriangle className="h-5 w-5 text-destructive" />
            </div>
            <AlertDialogTitle>Bereich löschen?</AlertDialogTitle>
          </div>
          <AlertDialogDescription className="space-y-3">
            <p>
              Sind Sie sicher, dass Sie den Bereich <strong>"{space.name}"</strong> löschen möchten?
            </p>
            {hasContent && (
              <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20">
                <p className="font-medium text-destructive">
                  Dieser Bereich enthält:
                </p>
                <ul className="mt-1 text-sm text-destructive/80 list-disc list-inside">
                  {space.documentCount > 0 && (
                    <li>{space.documentCount} Dokument{space.documentCount !== 1 ? 'e' : ''}</li>
                  )}
                  {space.folderCount > 0 && (
                    <li>{space.folderCount} Ordner</li>
                  )}
                </ul>
                <p className="mt-2 text-sm font-medium text-destructive">
                  Alle Inhalte werden unwiderruflich gelöscht!
                </p>
              </div>
            )}
            <div className="grid gap-2 pt-2">
              <Label htmlFor="confirm-delete">
                Geben Sie <strong>"{space.name}"</strong> ein, um zu bestätigen:
              </Label>
              <Input
                id="confirm-delete"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder={space.name}
                disabled={isLoading}
                aria-describedby={error ? 'delete-error' : undefined}
              />
            </div>
            {error && (
              <p id="delete-error" className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>Abbrechen</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={!isConfirmValid || isLoading}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Endgültig löschen
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export default DeleteSpaceDialog;
