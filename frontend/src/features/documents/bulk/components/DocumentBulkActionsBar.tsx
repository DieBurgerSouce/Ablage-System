/**
 * DocumentBulkActionsBar - Aktionsleiste für Massenoperationen auf Dokumenten
 *
 * Erscheint am unteren Bildschirmrand wenn Dokumente ausgewählt sind.
 * Bietet Schnellzugriff auf gaengige Bulk-Operationen.
 *
 * Features:
 * - Tag hinzufügen/entfernen Dialog
 * - Ordner verschieben Dialog
 * - Löschen mit Bestätigung
 * - Export Dialog
 * - Progress-Anzeige während Operation
 */

import * as React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  X,
  Trash2,
  Tag,
  FolderInput,
  Download,
  CheckSquare,
  Loader2,
  CheckCircle2,
  AlertCircle,
  FolderTree,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ExportFormat } from '../api';

// =============================================================================
// Types
// =============================================================================

export interface Folder {
  id: string;
  name: string;
  path?: string;
}

export interface DocumentBulkActionsBarProps {
  /** Anzahl ausgewählter Dokumente */
  selectedCount: number;
  /** Gesamtanzahl der Dokumente */
  totalCount?: number;
  /** Callback zum Aufheben der Auswahl */
  onClearSelection: () => void;
  /** Callback bei "Alle auswählen" */
  onSelectAll?: () => void;
  /** Verfügbare Ordner für Verschieben */
  folders?: Folder[];

  // Callbacks für Operationen
  onAddTags: (tags: string[]) => Promise<void>;
  onMoveToFolder: (folderId: string) => Promise<void>;
  onDelete: (reason?: string) => Promise<void>;
  onExport: (format: ExportFormat, includeMetadata: boolean) => Promise<void>;

  // Progress
  progress?: {
    action: string;
    current: number;
    total: number;
    status: 'running' | 'success' | 'error';
    message?: string;
  } | null;

  // Loading states
  isTagging?: boolean;
  isMoving?: boolean;
  isDeleting?: boolean;
  isExporting?: boolean;

  /** Zusätzliche CSS-Klassen */
  className?: string;
}

// =============================================================================
// Component
// =============================================================================

export function DocumentBulkActionsBar({
  selectedCount,
  totalCount,
  onClearSelection,
  onSelectAll,
  folders = [],
  onAddTags,
  onMoveToFolder,
  onDelete,
  onExport,
  progress,
  isTagging = false,
  isMoving = false,
  isDeleting = false,
  isExporting = false,
  className,
}: DocumentBulkActionsBarProps) {
  const isVisible = selectedCount > 0;
  const isAnyOperationPending = isTagging || isMoving || isDeleting || isExporting;

  // Dialog states
  const [tagDialogOpen, setTagDialogOpen] = React.useState(false);
  const [moveDialogOpen, setMoveDialogOpen] = React.useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false);
  const [exportDialogOpen, setExportDialogOpen] = React.useState(false);

  // Form states
  const [tagInput, setTagInput] = React.useState('');
  const [selectedFolderId, setSelectedFolderId] = React.useState<string>('');
  const [deleteReason, setDeleteReason] = React.useState('');
  const [exportFormat, setExportFormat] = React.useState<ExportFormat>('zip');
  const [includeMetadata, setIncludeMetadata] = React.useState(true);

  // Keyboard shortcuts
  React.useEffect(() => {
    if (!isVisible || isAnyOperationPending) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Escape to cancel selection
      if (e.key === 'Escape') {
        onClearSelection();
        return;
      }

      // Ctrl+A for select all
      if (e.ctrlKey && e.key === 'a' && onSelectAll) {
        e.preventDefault();
        onSelectAll();
        return;
      }

      // Ctrl+T for tags
      if (e.ctrlKey && e.key === 't') {
        e.preventDefault();
        setTagDialogOpen(true);
        return;
      }

      // Ctrl+M for move
      if (e.ctrlKey && e.key === 'm') {
        e.preventDefault();
        setMoveDialogOpen(true);
        return;
      }

      // Delete key
      if (e.key === 'Delete') {
        e.preventDefault();
        setDeleteDialogOpen(true);
        return;
      }

      // Ctrl+E for export
      if (e.ctrlKey && e.key === 'e') {
        e.preventDefault();
        setExportDialogOpen(true);
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isVisible, isAnyOperationPending, onClearSelection, onSelectAll]);

  // Handlers
  const handleAddTags = async () => {
    const tags = tagInput
      .split(',')
      .map((t) => t.trim())
      .filter((t) => t.length > 0);

    if (tags.length === 0) return;

    await onAddTags(tags);
    setTagInput('');
    setTagDialogOpen(false);
  };

  const handleMove = async () => {
    if (!selectedFolderId) return;
    await onMoveToFolder(selectedFolderId);
    setSelectedFolderId('');
    setMoveDialogOpen(false);
  };

  const handleDelete = async () => {
    await onDelete(deleteReason || undefined);
    setDeleteReason('');
    setDeleteDialogOpen(false);
  };

  const handleExport = async () => {
    await onExport(exportFormat, includeMetadata);
    setExportDialogOpen(false);
  };

  return (
    <>
      <AnimatePresence>
        {isVisible && (
          <motion.div
            initial={{ y: 100, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 100, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 500, damping: 40 }}
            className={cn(
              'fixed bottom-6 left-1/2 -translate-x-1/2 z-50',
              'flex items-center gap-2 px-4 py-3 rounded-xl',
              'bg-background/95 backdrop-blur-sm border shadow-lg',
              'min-w-[400px] max-w-[90vw]',
              className
            )}
          >
            {/* Selection Info */}
            <div className="flex items-center gap-2 pr-4 border-r">
              <CheckSquare className="h-5 w-5 text-primary" />
              <span className="font-medium whitespace-nowrap">
                {selectedCount} ausgewählt
                {totalCount && (
                  <span className="text-muted-foreground ml-1">von {totalCount}</span>
                )}
              </span>
            </div>

            {/* Progress indicator */}
            {progress && (
              <div className="flex items-center gap-3 px-3 min-w-[200px]">
                {progress.status === 'running' && (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                )}
                {progress.status === 'success' && (
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                )}
                {progress.status === 'error' && (
                  <AlertCircle className="h-4 w-4 text-destructive" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-muted-foreground mb-1">
                    {progress.message || progress.action}
                  </div>
                  <Progress value={(progress.current / progress.total) * 100} className="h-1" />
                </div>
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  {progress.current}/{progress.total}
                </span>
              </div>
            )}

            {/* Action Buttons */}
            {!progress && (
              <TooltipProvider delayDuration={300}>
                <div className="flex items-center gap-1">
                  {/* Tag Button */}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="gap-2 h-9"
                        onClick={() => setTagDialogOpen(true)}
                        disabled={isAnyOperationPending}
                      >
                        {isTagging ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Tag className="h-4 w-4" />
                        )}
                        <span className="hidden sm:inline">Tags</span>
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Tags hinzufügen</p>
                      <p className="text-xs text-muted-foreground">Strg+T</p>
                    </TooltipContent>
                  </Tooltip>

                  {/* Move Button */}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="gap-2 h-9"
                        onClick={() => setMoveDialogOpen(true)}
                        disabled={isAnyOperationPending || folders.length === 0}
                      >
                        {isMoving ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <FolderInput className="h-4 w-4" />
                        )}
                        <span className="hidden sm:inline">Verschieben</span>
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>In Ordner verschieben</p>
                      <p className="text-xs text-muted-foreground">Strg+M</p>
                    </TooltipContent>
                  </Tooltip>

                  {/* Export Button */}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="gap-2 h-9"
                        onClick={() => setExportDialogOpen(true)}
                        disabled={isAnyOperationPending}
                      >
                        {isExporting ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Download className="h-4 w-4" />
                        )}
                        <span className="hidden sm:inline">Exportieren</span>
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Dokumente exportieren</p>
                      <p className="text-xs text-muted-foreground">Strg+E</p>
                    </TooltipContent>
                  </Tooltip>

                  {/* Delete Button */}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="destructive"
                        size="sm"
                        className="gap-2 h-9"
                        onClick={() => setDeleteDialogOpen(true)}
                        disabled={isAnyOperationPending}
                      >
                        {isDeleting ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                        <span className="hidden sm:inline">Löschen</span>
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Dokumente löschen</p>
                      <p className="text-xs text-muted-foreground">Entf</p>
                    </TooltipContent>
                  </Tooltip>
                </div>
              </TooltipProvider>
            )}

            {/* Close Button */}
            <Button
              variant="ghost"
              size="sm"
              className="ml-2 h-8 w-8 p-0 rounded-full"
              onClick={onClearSelection}
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Auswahl aufheben</span>
            </Button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Tag Dialog */}
      <Dialog open={tagDialogOpen} onOpenChange={setTagDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Tags hinzufügen</DialogTitle>
            <DialogDescription>
              Tags werden zu {selectedCount} ausgewählten Dokument(en) hinzugefügt.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="tags">Tags (kommasepariert)</Label>
            <Input
              id="tags"
              placeholder="wichtig, archiv, rechnung"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddTags();
                }
              }}
              className="mt-2"
            />
            <p className="text-xs text-muted-foreground mt-2">
              Mehrere Tags mit Komma trennen
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTagDialogOpen(false)}>
              Abbrechen
            </Button>
            <Button onClick={handleAddTags} disabled={!tagInput.trim() || isTagging}>
              {isTagging && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Tags hinzufügen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Move Dialog */}
      <Dialog open={moveDialogOpen} onOpenChange={setMoveDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Dokumente verschieben</DialogTitle>
            <DialogDescription>
              {selectedCount} Dokument(e) in einen anderen Ordner verschieben.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="folder">Zielordner</Label>
            <Select value={selectedFolderId} onValueChange={setSelectedFolderId}>
              <SelectTrigger className="mt-2">
                <SelectValue placeholder="Ordner auswählen..." />
              </SelectTrigger>
              <SelectContent>
                {folders.map((folder) => (
                  <SelectItem key={folder.id} value={folder.id}>
                    <div className="flex items-center gap-2">
                      <FolderTree className="h-4 w-4" />
                      <span>{folder.name}</span>
                      {folder.path && (
                        <span className="text-xs text-muted-foreground">{folder.path}</span>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMoveDialogOpen(false)}>
              Abbrechen
            </Button>
            <Button onClick={handleMove} disabled={!selectedFolderId || isMoving}>
              {isMoving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Verschieben
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Export Dialog */}
      <Dialog open={exportDialogOpen} onOpenChange={setExportDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Dokumente exportieren</DialogTitle>
            <DialogDescription>
              {selectedCount} Dokument(e) exportieren.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4 space-y-4">
            <div>
              <Label htmlFor="format">Export-Format</Label>
              <Select
                value={exportFormat}
                onValueChange={(v) => setExportFormat(v as ExportFormat)}
              >
                <SelectTrigger className="mt-2">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="zip">ZIP-Archiv (alle Dateien)</SelectItem>
                  <SelectItem value="pdf">PDF (zusammengefügt)</SelectItem>
                  <SelectItem value="csv">CSV (nur Metadaten)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="metadata"
                checked={includeMetadata}
                onChange={(e) => setIncludeMetadata(e.target.checked)}
                className="h-4 w-4"
              />
              <Label htmlFor="metadata">Metadaten beilegen</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setExportDialogOpen(false)}>
              Abbrechen
            </Button>
            <Button onClick={handleExport} disabled={isExporting}>
              {isExporting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Exportieren
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Dokumente löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie wirklich {selectedCount} Dokument(e) löschen?
              <br />
              <br />
              Die Dokumente werden in den Papierkorb verschoben und können innerhalb von 30 Tagen
              wiederhergestellt werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="py-2">
            <Label htmlFor="reason">Loeschgrund (optional)</Label>
            <Input
              id="reason"
              placeholder="z.B. Nicht mehr benötigt"
              value={deleteReason}
              onChange={(e) => setDeleteReason(e.target.value)}
              className="mt-2"
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
