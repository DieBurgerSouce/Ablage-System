/**
 * AssignEditorDialog
 *
 * Dialog zur Zuweisung von Validierungs-Items an Editoren.
 * Zeigt verfügbare Editoren mit deren Workload an.
 */

import { useState, useCallback, useEffect } from 'react';
import { UserPlus, Users, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';

interface Editor {
  id: string;
  full_name: string;
  username: string;
  assigned_items_count: number;
}

interface AssignEditorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (editorId: string) => void;
  isLoading?: boolean;
  itemCount?: number;
  documentName?: string;
}

// API-Abfrage für verfügbare Editoren
function useAvailableEditors() {
  return useQuery({
    queryKey: ['validation', 'available-editors'],
    queryFn: async (): Promise<Editor[]> => {
      // Fallback auf User-Liste mit Editor/Admin-Rolle
      try {
        const response = await apiClient.get<{ users: Editor[] }>('/admin/users', {
          params: { role: 'admin', include_workload: true },
        });
        return response.data?.users || [];
      } catch {
        // Fallback: leere Liste, wenn Endpoint nicht existiert
        return [];
      }
    },
    staleTime: 30000, // 30 Sekunden Cache
  });
}

export function AssignEditorDialog({
  open,
  onOpenChange,
  onConfirm,
  isLoading = false,
  itemCount,
  documentName,
}: AssignEditorDialogProps) {
  const [selectedEditorId, setSelectedEditorId] = useState('');
  const { data: editors, isLoading: isLoadingEditors } = useAvailableEditors();

  // Reset bei Öffnen
  useEffect(() => {
    if (open) {
      setSelectedEditorId('');
    }
  }, [open]);

  const handleConfirm = useCallback(() => {
    if (!selectedEditorId) return;
    onConfirm(selectedEditorId);
  }, [selectedEditorId, onConfirm]);

  const handleClose = useCallback(() => {
    if (!isLoading) {
      onOpenChange(false);
      setSelectedEditorId('');
    }
  }, [isLoading, onOpenChange]);

  const isBatch = itemCount !== undefined && itemCount > 1;
  const title = isBatch
    ? `${itemCount} Dokumente zuweisen`
    : documentName
      ? `"${documentName}" zuweisen`
      : 'Dokument zuweisen';

  const description = isBatch
    ? `Wählen Sie einen Editor für ${itemCount} Dokumente.`
    : 'Wählen Sie einen Editor für die Validierung.';

  const selectedEditor = editors?.find((e) => e.id === selectedEditorId);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent
        className="sm:max-w-[450px]"
        aria-describedby="assign-editor-description"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserPlus className="w-5 h-5 text-primary" aria-hidden="true" />
            {title}
          </DialogTitle>
          <DialogDescription id="assign-editor-description">
            {description}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="editor-select">
              Editor <span className="text-destructive" aria-hidden="true">*</span>
              <span className="sr-only">(Pflichtfeld)</span>
            </Label>
            {isLoadingEditors ? (
              <div
                className="flex items-center gap-2 p-3 border rounded-md text-muted-foreground"
                role="status"
                aria-label="Lade verfügbare Editoren"
              >
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                <span>Lade Editoren...</span>
              </div>
            ) : editors && editors.length > 0 ? (
              <Select
                value={selectedEditorId}
                onValueChange={setSelectedEditorId}
              >
                <SelectTrigger
                  id="editor-select"
                  aria-label="Editor für Zuweisung auswählen"
                  aria-required="true"
                >
                  <SelectValue placeholder="Editor auswählen" />
                </SelectTrigger>
                <SelectContent>
                  {editors.map((editor) => (
                    <SelectItem key={editor.id} value={editor.id}>
                      <div className="flex items-center justify-between w-full gap-4">
                        <span>{editor.full_name || editor.username}</span>
                        <Badge variant="outline" className="ml-auto text-xs">
                          {editor.assigned_items_count} Items
                        </Badge>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div
                className="flex items-center gap-2 p-3 border rounded-md text-muted-foreground bg-muted/30"
                role="status"
                aria-label="Keine Editoren verfügbar"
              >
                <AlertCircle className="w-4 h-4" aria-hidden="true" />
                <span>Keine Editoren verfügbar</span>
              </div>
            )}
          </div>

          {selectedEditor && (
            <div
              className="p-3 bg-muted/30 rounded-md"
              role="region"
              aria-label="Ausgewählter Editor Details"
              aria-live="polite"
            >
              <div className="flex items-center gap-2 mb-2">
                <Users className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
                <span className="font-medium">
                  {selectedEditor.full_name || selectedEditor.username}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                Aktuell {selectedEditor.assigned_items_count} Items zugewiesen
              </p>
              {isBatch && (
                <p className="text-sm text-muted-foreground mt-1">
                  Nach Zuweisung: {selectedEditor.assigned_items_count + (itemCount || 0)} Items
                </p>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={isLoading}
            aria-label="Dialog schließen ohne Zuweisung"
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={isLoading || !selectedEditorId}
            aria-label={
              isBatch
                ? `${itemCount} Dokumente an ausgewählten Editor zuweisen`
                : documentName
                  ? `Dokument "${documentName}" zuweisen`
                  : 'Dokument zuweisen'
            }
            aria-busy={isLoading}
          >
            {isLoading
              ? 'Zuweisen...'
              : isBatch
                ? `${itemCount} zuweisen`
                : 'Zuweisen'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default AssignEditorDialog;
