/**
 * FinanceDocumentEditDialog
 *
 * Dialog zum Bearbeiten von Finanz-Dokumenten.
 * Ermöglicht die Bearbeitung von Metadaten und Finanz-spezifischen Feldern.
 */

import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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
import { useToast } from '@/components/ui/use-toast'
import { Loader2, Trash2, FileText } from 'lucide-react'
import {
  useUpdateFinanceDocument,
  useDeleteFinanceDocument,
} from '../hooks/use-finanzen-queries'
import {
  FINANCE_CATEGORIES,
  categoryHasDeadlines,
  categoryHasAmounts,
} from '../types'
import type { FinanceCategoryDocument, FinanceDocumentUpdateData } from '@/lib/api/services/finance'

interface FinanceDocumentEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  document: FinanceCategoryDocument | null
  yearId: string
  categoryId: string
}

interface FormData {
  category: string
  documentDate: string
  totalAmount: string
  nachzahlung: string
  erstattung: string
  einspruchsfrist: string
  aktenzeichen: string
  steuernummer: string
  finanzamt: string
  steuerart: string
  zeitraum: string
  versicherungsnummer: string
  vertragsnummer: string
}

export function FinanceDocumentEditDialog({
  open,
  onOpenChange,
  document,
  yearId,
  categoryId,
}: FinanceDocumentEditDialogProps) {
  const { toast } = useToast()
  const updateMutation = useUpdateFinanceDocument()
  const deleteMutation = useDeleteFinanceDocument()

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const hasAmounts = categoryHasAmounts(categoryId)
  const hasDeadlines = categoryHasDeadlines(categoryId)

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { isSubmitting, isDirty },
  } = useForm<FormData>({
    defaultValues: {
      category: categoryId,
      documentDate: '',
      totalAmount: '',
      nachzahlung: '',
      erstattung: '',
      einspruchsfrist: '',
      aktenzeichen: '',
      steuernummer: '',
      finanzamt: '',
      steuerart: 'none',
      zeitraum: '',
      versicherungsnummer: '',
      vertragsnummer: '',
    },
  })

  const category = watch('category')
  const steuerart = watch('steuerart')

  // Populate form when document changes
  useEffect(() => {
    if (open && document) {
      reset({
        category: categoryId,
        documentDate: document.documentDate ? document.documentDate.split('T')[0] : '',
        totalAmount: document.totalAmount?.toString() || '',
        nachzahlung: document.nachzahlung?.toString() || '',
        erstattung: document.erstattung?.toString() || '',
        einspruchsfrist: document.einspruchsfrist
          ? document.einspruchsfrist.split('T')[0]
          : '',
        aktenzeichen: document.aktenzeichen || '',
        steuernummer: document.steuernummer || '',
        finanzamt: document.finanzamt || '',
        steuerart: document.steuerart || 'none',
        zeitraum: document.zeitraum || '',
        versicherungsnummer: document.versicherungsnummer || '',
        vertragsnummer: document.vertragsnummer || '',
      })
    }
  }, [open, document, categoryId, reset])

  const onSubmit = async (data: FormData) => {
    if (!document) return

    try {
      const updateData: FinanceDocumentUpdateData = {}

      // Only include changed fields
      if (data.category !== categoryId) updateData.category = data.category
      if (data.documentDate) updateData.documentDate = data.documentDate
      if (data.totalAmount) updateData.totalAmount = parseFloat(data.totalAmount)
      if (data.nachzahlung) updateData.nachzahlung = parseFloat(data.nachzahlung)
      if (data.erstattung) updateData.erstattung = parseFloat(data.erstattung)
      if (data.einspruchsfrist) updateData.einspruchsfrist = data.einspruchsfrist
      if (data.aktenzeichen !== (document.aktenzeichen || '')) {
        updateData.aktenzeichen = data.aktenzeichen || undefined
      }
      if (data.steuernummer !== (document.steuernummer || '')) {
        updateData.steuernummer = data.steuernummer || undefined
      }
      if (data.finanzamt !== (document.finanzamt || '')) {
        updateData.finanzamt = data.finanzamt || undefined
      }
      if (data.steuerart !== (document.steuerart || 'none')) {
        updateData.steuerart = data.steuerart === 'none' ? undefined : data.steuerart
      }
      if (data.zeitraum !== (document.zeitraum || '')) {
        updateData.zeitraum = data.zeitraum || undefined
      }
      if (data.versicherungsnummer !== (document.versicherungsnummer || '')) {
        updateData.versicherungsnummer = data.versicherungsnummer || undefined
      }
      if (data.vertragsnummer !== (document.vertragsnummer || '')) {
        updateData.vertragsnummer = data.vertragsnummer || undefined
      }

      if (Object.keys(updateData).length === 0) {
        toast({
          title: 'Keine Änderungen',
          description: 'Es wurden keine Änderungen vorgenommen.',
        })
        return
      }

      await updateMutation.mutateAsync({
        documentId: document.id,
        updateData,
      })

      toast({
        title: 'Dokument aktualisiert',
        description: 'Die Änderungen wurden erfolgreich gespeichert.',
      })

      onOpenChange(false)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unbekannter Fehler'
      toast({
        title: 'Fehler beim Speichern',
        description: errorMessage,
        variant: 'destructive',
      })
    }
  }

  const handleDelete = async () => {
    if (!document) return

    try {
      await deleteMutation.mutateAsync({
        documentId: document.id,
        yearId,
        category: categoryId,
      })

      toast({
        title: 'Dokument gelöscht',
        description: 'Das Dokument wurde erfolgreich gelöscht.',
      })

      setShowDeleteConfirm(false)
      onOpenChange(false)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unbekannter Fehler'
      toast({
        title: 'Fehler beim Löschen',
        description: errorMessage,
        variant: 'destructive',
      })
    }
  }

  const handleClose = () => {
    reset()
    onOpenChange(false)
  }

  if (!document) return null

  return (
    <>
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3">
              <div className="p-2 bg-emerald-100 dark:bg-emerald-900 rounded-lg">
                <FileText className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              </div>
              Dokument bearbeiten
            </DialogTitle>
            <DialogDescription>
              <span className="font-medium">{document.originalFilename}</span>
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            {/* Kategorie ändern */}
            <div className="space-y-2">
              <Label>Kategorie</Label>
              <Select value={category} onValueChange={(value) => setValue('category', value)}>
                <SelectTrigger>
                  <SelectValue placeholder="Kategorie wählen" />
                </SelectTrigger>
                <SelectContent>
                  {FINANCE_CATEGORIES.map((cat) => (
                    <SelectItem key={cat.id} value={cat.id}>
                      {cat.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Basis-Metadaten */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="documentDate">Dokumentdatum</Label>
                <Input id="documentDate" type="date" {...register('documentDate')} />
              </div>

              {hasAmounts && (
                <div className="space-y-2">
                  <Label htmlFor="totalAmount">Gesamtbetrag (EUR)</Label>
                  <Input
                    id="totalAmount"
                    type="number"
                    step="0.01"
                    placeholder="0,00"
                    {...register('totalAmount')}
                  />
                </div>
              )}
            </div>

            {/* Steuer-spezifische Felder */}
            {hasAmounts && (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="nachzahlung">Nachzahlung (EUR)</Label>
                  <Input
                    id="nachzahlung"
                    type="number"
                    step="0.01"
                    placeholder="0,00"
                    className="text-red-600"
                    {...register('nachzahlung')}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="erstattung">Erstattung (EUR)</Label>
                  <Input
                    id="erstattung"
                    type="number"
                    step="0.01"
                    placeholder="0,00"
                    className="text-green-600"
                    {...register('erstattung')}
                  />
                </div>
              </div>
            )}

            {/* Fristen-Felder */}
            {hasDeadlines && (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="einspruchsfrist">Einspruchsfrist</Label>
                  <Input id="einspruchsfrist" type="date" {...register('einspruchsfrist')} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="aktenzeichen">Aktenzeichen</Label>
                  <Input
                    id="aktenzeichen"
                    placeholder="z.B. 123/456/78901"
                    {...register('aktenzeichen')}
                  />
                </div>
              </div>
            )}

            {/* Erweiterte Felder */}
            <div className="space-y-4 border-t pt-4">
              <h4 className="text-sm font-medium text-muted-foreground">Weitere Angaben</h4>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="steuernummer">Steuernummer</Label>
                  <Input
                    id="steuernummer"
                    placeholder="123/456/78901"
                    {...register('steuernummer')}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="finanzamt">Finanzamt</Label>
                  <Input id="finanzamt" placeholder="z.B. Koeln-Mitte" {...register('finanzamt')} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Steuerart</Label>
                  <Select
                    value={steuerart}
                    onValueChange={(value) => setValue('steuerart', value)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Steuerart wählen" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Keine</SelectItem>
                      <SelectItem value="einkommensteuer">Einkommensteuer</SelectItem>
                      <SelectItem value="koerperschaftsteuer">Körperschaftsteuer</SelectItem>
                      <SelectItem value="gewerbesteuer">Gewerbesteuer</SelectItem>
                      <SelectItem value="umsatzsteuer">Umsatzsteuer</SelectItem>
                      <SelectItem value="lohnsteuer">Lohnsteuer</SelectItem>
                      <SelectItem value="grundsteuer">Grundsteuer</SelectItem>
                      <SelectItem value="sonstige">Sonstige</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="zeitraum">Zeitraum</Label>
                  <Input
                    id="zeitraum"
                    placeholder="z.B. 2024 oder Q1/2024"
                    {...register('zeitraum')}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="versicherungsnummer">Versicherungsnummer</Label>
                  <Input
                    id="versicherungsnummer"
                    placeholder="V-123456789"
                    {...register('versicherungsnummer')}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="vertragsnummer">Vertragsnummer</Label>
                  <Input
                    id="vertragsnummer"
                    placeholder="VT-2024-001"
                    {...register('vertragsnummer')}
                  />
                </div>
              </div>
            </div>

            <DialogFooter className="flex justify-between pt-4">
              <Button
                type="button"
                variant="destructive"
                onClick={() => setShowDeleteConfirm(true)}
                className="gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Löschen
              </Button>

              <div className="flex gap-2">
                <Button type="button" variant="outline" onClick={handleClose}>
                  Abbrechen
                </Button>
                <Button
                  type="submit"
                  disabled={!isDirty || isSubmitting || updateMutation.isPending}
                  className="gap-2"
                >
                  {(isSubmitting || updateMutation.isPending) && (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  )}
                  {isSubmitting || updateMutation.isPending ? 'Speichern...' : 'Speichern'}
                </Button>
              </div>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Dokument löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Sind Sie sicher, dass Sie das Dokument{' '}
              <span className="font-medium">{document.originalFilename}</span> löschen möchten?
              Diese Aktion kann nicht rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  Löschen...
                </>
              ) : (
                'Löschen'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
