/**
 * CreateSpaceDialog - Dialog zum Erstellen eines neuen Privat-Bereichs
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Lock, Users, Loader2 } from 'lucide-react';
import type { PrivatSpaceCreate, PrivatSpaceType } from '@/types/privat';

interface CreateSpaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: PrivatSpaceCreate) => Promise<void>;
  isLoading?: boolean;
}

export function CreateSpaceDialog({
  open,
  onOpenChange,
  onSubmit,
  isLoading = false,
}: CreateSpaceDialogProps) {
  const [name, setName] = React.useState('');
  const [description, setDescription] = React.useState('');
  const [spaceType, setSpaceType] = React.useState<PrivatSpaceType>('personal');
  const [error, setError] = React.useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError('Name ist erforderlich');
      return;
    }

    if (name.length > 100) {
      setError('Name darf maximal 100 Zeichen lang sein');
      return;
    }

    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim() || undefined,
        spaceType,
      });
      // Reset form and close on success
      setName('');
      setDescription('');
      setSpaceType('personal');
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Erstellen');
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      // Reset form when closing
      setName('');
      setDescription('');
      setSpaceType('personal');
      setError(null);
    }
    onOpenChange(newOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Neuen Bereich erstellen</DialogTitle>
            <DialogDescription>
              Erstellen Sie einen neuen Bereich für Ihre Dokumente.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {/* Name */}
            <div className="grid gap-2">
              <Label htmlFor="name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z.B. Wichtige Dokumente"
                maxLength={100}
                disabled={isLoading}
                aria-describedby={error ? 'name-error' : undefined}
                aria-invalid={!!error}
              />
            </div>

            {/* Description */}
            <div className="grid gap-2">
              <Label htmlFor="description">Beschreibung</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optionale Beschreibung..."
                rows={2}
                maxLength={500}
                disabled={isLoading}
              />
            </div>

            {/* Space Type */}
            <div className="grid gap-2">
              <Label>Bereichstyp</Label>
              <RadioGroup
                value={spaceType}
                onValueChange={(value) => setSpaceType(value as PrivatSpaceType)}
                className="grid gap-3"
                disabled={isLoading}
              >
                <label
                  htmlFor="personal"
                  className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer hover:bg-muted/50 transition-colors [&:has(:checked)]:border-primary [&:has(:checked)]:bg-primary/5"
                >
                  <RadioGroupItem value="personal" id="personal" className="mt-1" />
                  <div className="flex items-start gap-3">
                    <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-950">
                      <Lock className="h-4 w-4 text-purple-600 dark:text-purple-400" />
                    </div>
                    <div>
                      <div className="font-medium">Persönlich</div>
                      <div className="text-sm text-muted-foreground">
                        Nur für Sie sichtbar und zugänglich
                      </div>
                    </div>
                  </div>
                </label>

                <label
                  htmlFor="shared"
                  className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer hover:bg-muted/50 transition-colors [&:has(:checked)]:border-primary [&:has(:checked)]:bg-primary/5"
                >
                  <RadioGroupItem value="shared" id="shared" className="mt-1" />
                  <div className="flex items-start gap-3">
                    <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-950">
                      <Users className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div>
                      <div className="font-medium">Geteilt</div>
                      <div className="text-sm text-muted-foreground">
                        Kann mit anderen Nutzern geteilt werden
                      </div>
                    </div>
                  </div>
                </label>
              </RadioGroup>
            </div>

            {/* Error message */}
            {error && (
              <p id="name-error" className="text-sm text-destructive" role="alert">
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
              Erstellen
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default CreateSpaceDialog;
