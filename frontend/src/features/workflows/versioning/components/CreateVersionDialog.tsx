/**
 * CreateVersionDialog Component
 *
 * Dialog zum Erstellen einer neuen Workflow-Version.
 */

import { useState } from 'react';
import { Plus, GitBranch } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { ChangeType } from '../types/version-types';
import { useCreateVersion } from '../hooks/useWorkflowVersions';
import { formatChangeType } from '@/lib/api/services/workflow-versions';

interface CreateVersionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workflowId: string;
  currentVersion?: string;
}

export function CreateVersionDialog({
  open,
  onOpenChange,
  workflowId,
  currentVersion,
}: CreateVersionDialogProps) {
  const [changeType, setChangeType] = useState<ChangeType>('minor');
  const [changeDescription, setChangeDescription] = useState('');
  const createMutation = useCreateVersion();

  const getNextVersion = () => {
    if (!currentVersion) return '1.0.0';

    const parts = currentVersion.split('.').map(Number);
    const [major, minor, patch] = parts;

    switch (changeType) {
      case 'major':
        return `${major + 1}.0.0`;
      case 'minor':
        return `${major}.${minor + 1}.0`;
      case 'patch':
        return `${major}.${minor}.${patch + 1}`;
      default:
        return currentVersion;
    }
  };

  const handleCreate = () => {
    if (!changeDescription.trim()) return;

    createMutation.mutate(
      {
        workflowId,
        data: {
          change_type: changeType,
          change_description: changeDescription.trim(),
        },
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          setChangeDescription('');
          setChangeType('minor');
        },
      }
    );
  };

  const changeTypeDescriptions: Record<ChangeType, string> = {
    major: 'Inkompatible Änderungen, neue Features',
    minor: 'Neue Features, rückwärtskompatibel',
    patch: 'Bugfixes, kleine Verbesserungen',
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitBranch className="h-5 w-5" />
            Neue Version erstellen
          </DialogTitle>
          <DialogDescription>
            Erstellen Sie eine neue Version des Workflows mit einer Beschreibung
            der Änderungen.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Current Version Info */}
          {currentVersion && (
            <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
              <span className="text-sm text-muted-foreground">Aktuelle Version</span>
              <span className="font-mono font-medium">v{currentVersion}</span>
            </div>
          )}

          {/* Change Type */}
          <div className="space-y-2">
            <Label htmlFor="changeType">Änderungstyp</Label>
            <Select
              value={changeType}
              onValueChange={(value) => setChangeType(value as ChangeType)}
            >
              <SelectTrigger id="changeType">
                <SelectValue placeholder="Typ wählen" />
              </SelectTrigger>
              <SelectContent>
                {(['major', 'minor', 'patch'] as ChangeType[]).map((type) => (
                  <SelectItem key={type} value={type}>
                    <div className="flex flex-col items-start">
                      <span className="font-medium">{formatChangeType(type)}</span>
                      <span className="text-xs text-muted-foreground">
                        {changeTypeDescriptions[type]}
                      </span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* New Version Preview */}
          <div className="flex items-center justify-between p-3 bg-primary/10 rounded-lg">
            <span className="text-sm">Neue Version</span>
            <span className="font-mono font-medium text-primary">
              v{getNextVersion()}
            </span>
          </div>

          {/* Change Description */}
          <div className="space-y-2">
            <Label htmlFor="changeDescription">Änderungsbeschreibung *</Label>
            <Textarea
              id="changeDescription"
              value={changeDescription}
              onChange={(e) => setChangeDescription(e.target.value)}
              placeholder="Beschreiben Sie die Änderungen in dieser Version..."
              rows={4}
            />
            <p className="text-xs text-muted-foreground">
              Diese Beschreibung hilft bei der Nachverfolgung von Änderungen.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={createMutation.isPending}
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleCreate}
            disabled={!changeDescription.trim() || createMutation.isPending}
          >
            {createMutation.isPending ? (
              'Wird erstellt...'
            ) : (
              <>
                <Plus className="h-4 w-4 mr-2" />
                Version erstellen
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
