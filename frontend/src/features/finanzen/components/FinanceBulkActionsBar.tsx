/**
 * FinanceBulkActionsBar - Aktionsleiste für Bulk-Operationen
 *
 * Wird angezeigt wenn Dokumente ausgewählt sind.
 * Ermöglicht:
 * - Bulk Delete
 * - Bulk Edit (Kategorie/Jahr ändern)
 * - Export
 */

import { useState } from 'react'
import { Trash2, Edit, Download, X, AlertTriangle, Loader2, CheckCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { useToast } from '@/components/ui/use-toast'
import { financeService, type FinanceBulkUpdateData } from '@/lib/api/services/finance'
import { FINANCE_CATEGORIES, FINANCE_PACKAGES } from '../types'

interface FinanceBulkActionsBarProps {
  selectedIds: string[]
  onClearSelection: () => void
  onActionComplete: () => void
  currentYear?: string
  currentCategory?: string
}

export function FinanceBulkActionsBar({
  selectedIds,
  onClearSelection,
  onActionComplete,
  currentYear: _currentYear,
  currentCategory: _currentCategory,
}: FinanceBulkActionsBarProps) {
  void _currentYear
  void _currentCategory
  const { toast } = useToast()
  const [isDeleting, setIsDeleting] = useState(false)
  const [isUpdating, setIsUpdating] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [showExportDialog, setShowExportDialog] = useState(false)

  // Edit Form State
  const [editCategory, setEditCategory] = useState<string>('')
  const [editYear, setEditYear] = useState<string>('')

  const count = selectedIds.length

  // Bulk Delete Handler
  const handleBulkDelete = async () => {
    setIsDeleting(true)
    try {
      const result = await financeService.bulkDeleteDocuments(selectedIds)

      if (result.failedCount > 0) {
        toast({
          title: 'Teilerfolg',
          description: `${result.deletedCount} gelöscht, ${result.failedCount} fehlgeschlagen`,
          variant: 'default',
        })
      } else {
        toast({
          title: 'Erfolgreich gelöscht',
          description: `${result.deletedCount} Dokumente wurden gelöscht`,
        })
      }

      onClearSelection()
      onActionComplete()
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Bulk-Löschung fehlgeschlagen',
        variant: 'destructive',
      })
    } finally {
      setIsDeleting(false)
      setShowDeleteDialog(false)
    }
  }

  // Bulk Edit Handler
  const handleBulkEdit = async () => {
    const updateData: FinanceBulkUpdateData = {}
    if (editCategory) updateData.category = editCategory
    if (editYear) updateData.year = parseInt(editYear, 10)

    if (!updateData.category && !updateData.year) {
      toast({
        title: 'Keine Änderungen',
        description: 'Bitte wählen Sie mindestens ein Feld zum Ändern',
        variant: 'destructive',
      })
      return
    }

    setIsUpdating(true)
    try {
      const result = await financeService.bulkUpdateDocuments(selectedIds, updateData)

      if (result.failedCount > 0) {
        toast({
          title: 'Teilerfolg',
          description: `${result.updatedCount} aktualisiert, ${result.failedCount} fehlgeschlagen`,
          variant: 'default',
        })
      } else {
        toast({
          title: 'Erfolgreich aktualisiert',
          description: `${result.updatedCount} Dokumente wurden aktualisiert`,
        })
      }

      onClearSelection()
      onActionComplete()
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Bulk-Aktualisierung fehlgeschlagen',
        variant: 'destructive',
      })
    } finally {
      setIsUpdating(false)
      setShowEditDialog(false)
      setEditCategory('')
      setEditYear('')
    }
  }

  // Export Handler
  const handleExport = async () => {
    setIsExporting(true)
    try {
      const result = await financeService.exportDocuments({
        documentIds: selectedIds,
        format: 'zip',
        includeFiles: true,
      })

      toast({
        title: 'Export gestartet',
        description: result.message,
      })

      // In Produktion: Polling für Download-URL oder WebSocket
      onClearSelection()
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Export fehlgeschlagen',
        variant: 'destructive',
      })
    } finally {
      setIsExporting(false)
      setShowExportDialog(false)
    }
  }

  if (count === 0) return null

  // Jahre für Dropdown (letzten 10 Jahre)
  const years = Array.from({ length: 10 }, (_, i) => {
    const year = new Date().getFullYear() - i
    return { value: String(year), label: String(year) }
  })

  return (
    <>
      {/* Floating Action Bar */}
      <div
        className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50
                   bg-background/95 backdrop-blur-sm border rounded-lg shadow-lg
                   px-4 py-3 flex items-center gap-4
                   animate-in slide-in-from-bottom-4 duration-200"
        role="toolbar"
        aria-label="Bulk-Aktionen"
      >
        {/* Selection Count */}
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="font-mono">
            {count}
          </Badge>
          <span className="text-sm text-muted-foreground">
            {count === 1 ? 'Dokument' : 'Dokumente'} ausgewählt
          </span>
        </div>

        {/* Divider */}
        <div className="h-6 w-px bg-border" />

        {/* Actions */}
        <div className="flex items-center gap-2" role="group" aria-label="Bulk-Aktionen">
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => setShowEditDialog(true)}
            disabled={isUpdating}
            aria-label={`${count} Dokumente bearbeiten`}
          >
            <Edit className="w-4 h-4" aria-hidden="true" />
            <span className="hidden sm:inline">Bearbeiten</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => setShowExportDialog(true)}
            disabled={isExporting}
            aria-label={`${count} Dokumente exportieren`}
          >
            <Download className="w-4 h-4" aria-hidden="true" />
            <span className="hidden sm:inline">Exportieren</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="gap-2 text-destructive hover:text-destructive"
            onClick={() => setShowDeleteDialog(true)}
            disabled={isDeleting}
            aria-label={`${count} Dokumente löschen`}
          >
            <Trash2 className="w-4 h-4" aria-hidden="true" />
            <span className="hidden sm:inline">Löschen</span>
          </Button>
        </div>

        {/* Divider */}
        <div className="h-6 w-px bg-border" />

        {/* Clear Selection */}
        <Button
          variant="ghost"
          size="sm"
          className="gap-1"
          onClick={onClearSelection}
          aria-label="Auswahl aufheben"
        >
          <X className="w-4 h-4" />
        </Button>
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-destructive" />
              {count} Dokumente löschen?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Diese Aktion kann nicht rückgängig gemacht werden.
              Die ausgewählten Dokumente werden dauerhaft gelöscht.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleBulkDelete}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Lösche...
                </>
              ) : (
                <>
                  <Trash2 className="w-4 h-4 mr-2" />
                  Löschen
                </>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Edit Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {count} Dokumente bearbeiten
            </DialogTitle>
            <DialogDescription>
              Wählen Sie die Felder aus, die für alle ausgewählten Dokumente geändert werden sollen.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-category">Kategorie</Label>
              <Select value={editCategory} onValueChange={setEditCategory}>
                <SelectTrigger id="edit-category">
                  <SelectValue placeholder="Kategorie auswählen..." />
                </SelectTrigger>
                <SelectContent>
                  {FINANCE_PACKAGES.map((pkg) => (
                    <div key={pkg.id}>
                      <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                        {pkg.label}
                      </div>
                      {FINANCE_CATEGORIES.filter((cat) => cat.package === pkg.id).map((cat) => (
                        <SelectItem key={cat.id} value={cat.id}>
                          {cat.label}
                        </SelectItem>
                      ))}
                    </div>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit-year">Jahr</Label>
              <Select value={editYear} onValueChange={setEditYear}>
                <SelectTrigger id="edit-year">
                  <SelectValue placeholder="Jahr auswählen..." />
                </SelectTrigger>
                <SelectContent>
                  {years.map((y) => (
                    <SelectItem key={y.value} value={y.value}>
                      {y.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)} disabled={isUpdating}>
              Abbrechen
            </Button>
            <Button onClick={handleBulkEdit} disabled={isUpdating || (!editCategory && !editYear)}>
              {isUpdating ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Aktualisiere...
                </>
              ) : (
                <>
                  <CheckCircle className="w-4 h-4 mr-2" />
                  Anwenden
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Export Dialog */}
      <Dialog open={showExportDialog} onOpenChange={setShowExportDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {count} Dokumente exportieren
            </DialogTitle>
            <DialogDescription>
              Die ausgewählten Dokumente werden als ZIP-Archiv exportiert.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            <div className="rounded-lg border p-4 bg-muted/50">
              <div className="flex items-center gap-3">
                <Download className="w-8 h-8 text-muted-foreground" />
                <div>
                  <p className="font-medium">{count} Dokumente</p>
                  <p className="text-sm text-muted-foreground">
                    inkl. Metadaten und Original-Dateien
                  </p>
                </div>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowExportDialog(false)} disabled={isExporting}>
              Abbrechen
            </Button>
            <Button onClick={handleExport} disabled={isExporting}>
              {isExporting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Exportiere...
                </>
              ) : (
                <>
                  <Download className="w-4 h-4 mr-2" />
                  Export starten
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default FinanceBulkActionsBar
