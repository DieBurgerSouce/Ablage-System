/**
 * BulkActionsToolbar - Fixed Bottom Bar für Bulk-Aktionen
 *
 * Features:
 * - Wird nur angezeigt wenn selectedCount > 0
 * - Download als ZIP
 * - Export als CSV
 * - Löschen mit Bestätigung
 * - In Ordner verschieben
 * - Tags bearbeiten
 * - Status ändern
 * - Selection-Counter und Clear-Button
 * - Animiertes Ein/Ausblenden
 * - WCAG 2.1 AA konform (Focus-Management, ARIA)
 */

import { useState, useEffect, useRef } from 'react';
import {
  Download,
  FileSpreadsheet,
  Trash2,
  X,
  CheckCircle2,
  Loader2,
  AlertTriangle,
  FolderInput,
  Tags,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
import { cn } from '@/lib/utils';
import {
  useBulkDownloadZip,
  useBulkExportCsv,
  useBulkDelete,
  useBulkMarkAsPaid,
} from '../hooks/use-ablage-queries';
import { CATEGORIES_WITH_PAYMENT_STATUS } from '../types';
import { MoveFolderDialog } from './MoveFolderDialog';
import { TagsEditDialog } from './TagsEditDialog';
import { StatusChangeDropdown } from './StatusChangeDropdown';

// ==================== Types ====================

interface BulkActionsToolbarProps {
  selectedIds: string[];
  category: string;
  entityType: 'customer' | 'supplier';
  folderId: string;
  onClearSelection: () => void;
  className?: string;
}

// ==================== Main Component ====================

export function BulkActionsToolbar({
  selectedIds,
  category,
  entityType,
  folderId,
  onClearSelection,
  className,
}: BulkActionsToolbarProps) {
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [moveFolderDialogOpen, setMoveFolderDialogOpen] = useState(false);
  const [tagsDialogOpen, setTagsDialogOpen] = useState(false);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const wasVisible = useRef(false);

  // Mutations
  const downloadZip = useBulkDownloadZip();
  const exportCsv = useBulkExportCsv();
  const bulkDelete = useBulkDelete();
  const bulkMarkAsPaid = useBulkMarkAsPaid();

  // Check if any operation is in progress
  const isLoading =
    downloadZip.isPending ||
    exportCsv.isPending ||
    bulkDelete.isPending ||
    bulkMarkAsPaid.isPending;

  // Show payment actions only for invoice-related categories
  const showPaymentActions = CATEGORIES_WITH_PAYMENT_STATUS.includes(category);

  const isVisible = selectedIds.length > 0;

  // Focus management: Focus toolbar when it appears
  useEffect(() => {
    if (isVisible && !wasVisible.current && toolbarRef.current) {
      // Announce to screen readers
      const announcement = document.createElement('div');
      announcement.setAttribute('role', 'status');
      announcement.setAttribute('aria-live', 'polite');
      announcement.className = 'sr-only';
      announcement.textContent = `${selectedIds.length} Dokumente ausgewählt. Bulk-Aktionen verfügbar.`;
      document.body.appendChild(announcement);
      setTimeout(() => announcement.remove(), 1000);
    }
    wasVisible.current = isVisible;
  }, [isVisible, selectedIds.length]);

  // Don't render if nothing selected
  if (!isVisible) {
    return null;
  }

  // Handle ZIP download
  const handleDownloadZip = async () => {
    await downloadZip.mutateAsync({ documentIds: selectedIds });
    onClearSelection();
  };

  // Handle CSV export
  const handleExportCsv = async () => {
    await exportCsv.mutateAsync({ documentIds: selectedIds });
    onClearSelection();
  };

  // Handle delete
  const handleDelete = async () => {
    await bulkDelete.mutateAsync({ documentIds: selectedIds });
    setDeleteDialogOpen(false);
    onClearSelection();
  };

  // Handle mark as paid
  const handleMarkAsPaid = async () => {
    await bulkMarkAsPaid.mutateAsync({ documentIds: selectedIds });
    onClearSelection();
  };

  return (
    <>
      {/* Fixed Bottom Bar */}
      <div
        ref={toolbarRef}
        data-testid="bulk-actions-toolbar"
        className={cn(
          'fixed bottom-0 left-0 right-0 z-50',
          'border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80',
          'shadow-lg',
          'animate-in slide-in-from-bottom-4 duration-300',
          className
        )}
        role="toolbar"
        aria-label={`Bulk-Aktionen für ${selectedIds.length} ausgewählte Dokumente`}
      >
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            {/* Selection Info */}
            <div className="flex items-center gap-3">
              <Badge variant="secondary" className="h-7 px-3 text-sm" aria-live="polite">
                {selectedIds.length} ausgewählt
              </Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={onClearSelection}
                disabled={isLoading}
                aria-label="Auswahl aller Dokumente aufheben"
              >
                <X className="h-4 w-4 mr-1" aria-hidden="true" />
                Auswahl aufheben
              </Button>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2" role="group" aria-label="Verfügbare Aktionen">
              {/* Move to Folder */}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setMoveFolderDialogOpen(true)}
                disabled={isLoading}
                aria-label={`${selectedIds.length} Dokumente verschieben`}
              >
                <FolderInput className="h-4 w-4 mr-2" aria-hidden="true" />
                Verschieben
              </Button>

              {/* Edit Tags */}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setTagsDialogOpen(true)}
                disabled={isLoading}
                aria-label={`Tags für ${selectedIds.length} Dokumente bearbeiten`}
              >
                <Tags className="h-4 w-4 mr-2" aria-hidden="true" />
                Tags
              </Button>

              {/* Status Change Dropdown */}
              <StatusChangeDropdown
                selectedIds={selectedIds}
                showPaymentStatus={showPaymentActions}
                disabled={isLoading}
                onSuccess={onClearSelection}
              />

              {/* Mark as Paid (only for invoices) - Quick Action */}
              {showPaymentActions && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleMarkAsPaid}
                  disabled={isLoading}
                  className="text-green-600 hover:text-green-700 hover:bg-green-50"
                  aria-label={`${selectedIds.length} Dokumente als bezahlt markieren`}
                >
                  {bulkMarkAsPaid.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4 mr-2" aria-hidden="true" />
                  )}
                  {bulkMarkAsPaid.isPending ? 'Wird verarbeitet...' : 'Als bezahlt markieren'}
                </Button>
              )}

              {/* Download ZIP */}
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownloadZip}
                disabled={isLoading}
                aria-label={`${selectedIds.length} Dokumente als ZIP herunterladen`}
              >
                {downloadZip.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
                ) : (
                  <Download className="h-4 w-4 mr-2" aria-hidden="true" />
                )}
                {downloadZip.isPending ? 'Wird erstellt...' : 'ZIP herunterladen'}
              </Button>

              {/* Export CSV */}
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportCsv}
                disabled={isLoading}
                aria-label={`${selectedIds.length} Dokumente als CSV exportieren`}
              >
                {exportCsv.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
                ) : (
                  <FileSpreadsheet className="h-4 w-4 mr-2" aria-hidden="true" />
                )}
                {exportCsv.isPending ? 'Wird exportiert...' : 'CSV exportieren'}
              </Button>

              {/* Delete */}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeleteDialogOpen(true)}
                disabled={isLoading}
                className="text-destructive hover:text-destructive hover:bg-destructive/10"
                aria-label={`${selectedIds.length} Dokumente löschen`}
              >
                {bulkDelete.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" aria-hidden="true" />
                )}
                {bulkDelete.isPending ? 'Wird gelöscht...' : 'Löschen'}
              </Button>
            </div>
          </div>

          {/* Error Messages */}
          {(downloadZip.isError || exportCsv.isError || bulkDelete.isError || bulkMarkAsPaid.isError) && (
            <div className="mt-2 flex items-center gap-2 text-sm text-destructive" role="alert" aria-live="assertive">
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              <span>
                Fehler bei der Ausführung. Bitte versuchen Sie es erneut.
              </span>
            </div>
          )}

          {/* Success Messages */}
          {bulkDelete.isSuccess && (
            <div className="mt-2 flex items-center gap-2 text-sm text-green-600" role="status" aria-live="polite">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              <span>
                {bulkDelete.data.successCount} Dokumente gelöscht
                {bulkDelete.data.failedCount > 0 && `, ${bulkDelete.data.failedCount} fehlgeschlagen`}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent aria-describedby="delete-dialog-description">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Trash2 className="h-5 w-5 text-destructive" aria-hidden="true" />
              Dokumente löschen?
            </AlertDialogTitle>
            <AlertDialogDescription id="delete-dialog-description">
              Möchten Sie wirklich{' '}
              <span className="font-semibold">{selectedIds.length} Dokumente</span>{' '}
              löschen? Diese Aktion kann nicht rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={bulkDelete.isPending}>
              Abbrechen
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={bulkDelete.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              aria-label={`${selectedIds.length} Dokumente endgültig löschen`}
            >
              {bulkDelete.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" aria-hidden="true" />
              )}
              {bulkDelete.isPending ? 'Wird gelöscht...' : 'Endgültig löschen'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Move to Folder Dialog */}
      <MoveFolderDialog
        open={moveFolderDialogOpen}
        onOpenChange={setMoveFolderDialogOpen}
        selectedIds={selectedIds}
        currentCategory={category}
        entityType={entityType}
        folderId={folderId}
        onSuccess={onClearSelection}
      />

      {/* Tags Edit Dialog */}
      <TagsEditDialog
        open={tagsDialogOpen}
        onOpenChange={setTagsDialogOpen}
        selectedIds={selectedIds}
        onSuccess={onClearSelection}
      />
    </>
  );
}

export default BulkActionsToolbar;
