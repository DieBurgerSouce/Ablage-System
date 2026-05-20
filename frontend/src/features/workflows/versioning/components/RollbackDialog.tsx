/**
 * RollbackDialog Component
 *
 * Bestätigung für Rollback zu einer vorherigen Version.
 */

import { useState } from 'react';
import { AlertTriangle, RotateCcw, Shield } from 'lucide-react';
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
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import type { WorkflowVersion } from '../types/version-types';
import { useRollback } from '../hooks/useWorkflowVersions';
import { VersionBadge } from './VersionBadge';

interface RollbackDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workflowId: string;
  targetVersion: WorkflowVersion | null;
  currentActiveVersion?: WorkflowVersion | null;
}

export function RollbackDialog({
  open,
  onOpenChange,
  workflowId,
  targetVersion,
  currentActiveVersion,
}: RollbackDialogProps) {
  const [createBackup, setCreateBackup] = useState(true);
  const rollbackMutation = useRollback();

  const handleRollback = () => {
    if (!targetVersion) return;

    rollbackMutation.mutate(
      {
        workflowId,
        data: {
          target_version_id: targetVersion.id,
          create_backup: createBackup,
        },
      },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
      }
    );
  };

  if (!targetVersion) return null;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-w-lg">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <RotateCcw className="h-5 w-5 text-yellow-600" />
            Rollback bestätigen
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-4 text-left">
              <p>
                Sie sind dabei, den Workflow auf eine vorherige Version
                zurückzusetzen. Diese Aktion ändert die aktive Version.
              </p>

              <div className="bg-muted p-4 rounded-lg space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Ziel-Version</span>
                  <Badge variant="outline" className="font-mono">
                    v{targetVersion.version}
                  </Badge>
                </div>
                {currentActiveVersion && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">
                      Aktuelle Version
                    </span>
                    <Badge variant="outline" className="font-mono">
                      v{currentActiveVersion.version}
                    </Badge>
                  </div>
                )}
                <div className="flex items-start gap-2 pt-2 border-t">
                  <span className="text-sm text-muted-foreground">Status</span>
                  <VersionBadge status={targetVersion.status} />
                </div>
              </div>

              <div className="flex items-start gap-3 p-3 bg-yellow-50 dark:bg-yellow-950 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                <AlertTriangle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                <div className="text-sm">
                  <p className="font-medium text-yellow-800 dark:text-yellow-200">
                    Warnung
                  </p>
                  <p className="text-yellow-700 dark:text-yellow-300 mt-1">
                    Der Rollback erstellt eine neue Version basierend auf der
                    ausgewählten Version und aktiviert diese sofort. Laufende
                    Ausführungen werden nicht beeinflusst.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <Checkbox
                  id="createBackup"
                  checked={createBackup}
                  onCheckedChange={(checked) => setCreateBackup(checked === true)}
                />
                <Label
                  htmlFor="createBackup"
                  className="text-sm flex items-center gap-2"
                >
                  <Shield className="h-4 w-4 text-green-600" />
                  Backup der aktuellen Version erstellen (empfohlen)
                </Label>
              </div>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={rollbackMutation.isPending}>
            Abbrechen
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={handleRollback}
            disabled={rollbackMutation.isPending}
            className="bg-yellow-600 hover:bg-yellow-700"
          >
            {rollbackMutation.isPending ? (
              'Wird zurückgesetzt...'
            ) : (
              <>
                <RotateCcw className="h-4 w-4 mr-2" />
                Rollback durchführen
              </>
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
