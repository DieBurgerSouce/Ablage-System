/**
 * EditSpaceDialog - Dialog zum Bearbeiten eines Privat-Bereichs
 */

import * as React from 'react';
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
import { Loader2 } from 'lucide-react';
import type { PrivatSpaceWithStats, PrivatSpaceUpdate } from '@/types/privat';

interface EditSpaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  space: PrivatSpaceWithStats | null;
  onSubmit: (spaceId: string, data: PrivatSpaceUpdate) => Promise<void>;
  isLoading?: boolean;
}

export function EditSpaceDialog({
  open,
  onOpenChange,
  space,
  onSubmit,
  isLoading = false,
}: EditSpaceDialogProps) {
  const [name, setName] = React.useState('');
  const [description, setDescription] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);

  // Initialize form when space changes
  React.useEffect(() => {
    if (space) {
      setName(space.name);
      setDescription(space.description || '');
    }
  }, [space]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!space) return;

    if (!name.trim()) {
      setError('Name ist erforderlich');
      return;
    }

    if (name.length > 100) {
      setError('Name darf maximal 100 Zeichen lang sein');
      return;
    }

    try {
      await onSubmit(space.id, {
        name: name.trim(),
        description: description.trim() || undefined,
      });
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Speichern');
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      setError(null);
    }
    onOpenChange(newOpen);
  };

  if (!space) return null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Bereich bearbeiten</DialogTitle>
            <DialogDescription>
              Aendern Sie den Namen und die Beschreibung des Bereichs.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {/* Name */}
            <div className="grid gap-2">
              <Label htmlFor="edit-name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="edit-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z.B. Wichtige Dokumente"
                maxLength={100}
                disabled={isLoading}
                aria-describedby={error ? 'edit-name-error' : undefined}
                aria-invalid={!!error}
              />
            </div>

            {/* Description */}
            <div className="grid gap-2">
              <Label htmlFor="edit-description">Beschreibung</Label>
              <Textarea
                id="edit-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optionale Beschreibung..."
                rows={2}
                maxLength={500}
                disabled={isLoading}
              />
            </div>

            {/* Error message */}
            {error && (
              <p id="edit-name-error" className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isLoading}
            >
              Abbrechen
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Speichern
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default EditSpaceDialog;
