/**
 * FinanceFilterDialog
 *
 * Dialog zur erweiterten Filterung von Finanz-Dokumenten.
 * Bietet Filter nach Datum, Betrag, Steuerart und Status.
 */

import { useEffect } from 'react'
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
import { Filter, X } from 'lucide-react'
import { categoryHasAmounts, categoryHasDeadlines } from '../types'

export interface FilterValues {
  dateFrom?: string
  dateTo?: string
  amountMin?: number
  amountMax?: number
  steuerart?: string
  sortBy: string
  sortOrder: 'asc' | 'desc'
}

interface FinanceFilterDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  categoryId: string
  currentFilters: FilterValues
  onApplyFilters: (filters: FilterValues) => void
}

interface FormData {
  dateFrom: string
  dateTo: string
  amountMin: string
  amountMax: string
  steuerart: string
  sortBy: string
  sortOrder: 'asc' | 'desc'
}

export function FinanceFilterDialog({
  open,
  onOpenChange,
  categoryId,
  currentFilters,
  onApplyFilters,
}: FinanceFilterDialogProps) {
  const hasAmounts = categoryHasAmounts(categoryId)
  const hasDeadlines = categoryHasDeadlines(categoryId)

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
  } = useForm<FormData>({
    defaultValues: {
      dateFrom: '',
      dateTo: '',
      amountMin: '',
      amountMax: '',
      steuerart: 'all',
      sortBy: 'document_date',
      sortOrder: 'desc',
    },
  })

  const sortBy = watch('sortBy')
  const sortOrder = watch('sortOrder')
  const steuerart = watch('steuerart')

  // Populate form with current filters
  useEffect(() => {
    if (open) {
      reset({
        dateFrom: currentFilters.dateFrom || '',
        dateTo: currentFilters.dateTo || '',
        amountMin: currentFilters.amountMin?.toString() || '',
        amountMax: currentFilters.amountMax?.toString() || '',
        steuerart: currentFilters.steuerart || '',
        sortBy: currentFilters.sortBy || 'document_date',
        sortOrder: currentFilters.sortOrder || 'desc',
      })
    }
  }, [open, currentFilters, reset])

  const onSubmit = (data: FormData) => {
    const filters: FilterValues = {
      sortBy: data.sortBy,
      sortOrder: data.sortOrder,
    }

    if (data.dateFrom) filters.dateFrom = data.dateFrom
    if (data.dateTo) filters.dateTo = data.dateTo
    if (data.amountMin) filters.amountMin = parseFloat(data.amountMin)
    if (data.amountMax) filters.amountMax = parseFloat(data.amountMax)
    if (data.steuerart && data.steuerart !== 'all') filters.steuerart = data.steuerart

    onApplyFilters(filters)
    onOpenChange(false)
  }

  const handleReset = () => {
    const defaultFilters: FilterValues = {
      sortBy: 'document_date',
      sortOrder: 'desc',
    }
    onApplyFilters(defaultFilters)
    reset({
      dateFrom: '',
      dateTo: '',
      amountMin: '',
      amountMax: '',
      steuerart: 'all',
      sortBy: 'document_date',
      sortOrder: 'desc',
    })
    onOpenChange(false)
  }

  const handleClose = () => {
    onOpenChange(false)
  }

  // Count active filters
  const activeFilterCount = [
    currentFilters.dateFrom,
    currentFilters.dateTo,
    currentFilters.amountMin,
    currentFilters.amountMax,
    currentFilters.steuerart,
  ].filter(Boolean).length

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Filter className="w-5 h-5" />
            Filter
            {activeFilterCount > 0 && (
              <span className="ml-2 px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300 rounded-full">
                {activeFilterCount} aktiv
              </span>
            )}
          </DialogTitle>
          <DialogDescription>
            Filtern und sortieren Sie die Dokumente nach verschiedenen Kriterien.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          {/* Datumsbereich */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Dokumentdatum</Label>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="dateFrom" className="text-xs text-muted-foreground">
                  Von
                </Label>
                <Input id="dateFrom" type="date" {...register('dateFrom')} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="dateTo" className="text-xs text-muted-foreground">
                  Bis
                </Label>
                <Input id="dateTo" type="date" {...register('dateTo')} />
              </div>
            </div>
          </div>

          {/* Betragsbereich */}
          {hasAmounts && (
            <div className="space-y-3">
              <Label className="text-sm font-medium">Betrag (EUR)</Label>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="amountMin" className="text-xs text-muted-foreground">
                    Minimum
                  </Label>
                  <Input
                    id="amountMin"
                    type="number"
                    step="0.01"
                    placeholder="0,00"
                    {...register('amountMin')}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="amountMax" className="text-xs text-muted-foreground">
                    Maximum
                  </Label>
                  <Input
                    id="amountMax"
                    type="number"
                    step="0.01"
                    placeholder="0,00"
                    {...register('amountMax')}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Steuerart */}
          {hasDeadlines && (
            <div className="space-y-2">
              <Label>Steuerart</Label>
              <Select value={steuerart} onValueChange={(value) => setValue('steuerart', value)}>
                <SelectTrigger>
                  <SelectValue placeholder="Alle Steuerarten" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Alle Steuerarten</SelectItem>
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
          )}

          {/* Sortierung */}
          <div className="space-y-3 border-t pt-4">
            <Label className="text-sm font-medium">Sortierung</Label>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Sortieren nach</Label>
                <Select value={sortBy} onValueChange={(value) => setValue('sortBy', value)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="document_date">Dokumentdatum</SelectItem>
                    <SelectItem value="created_at">Hochgeladen am</SelectItem>
                    <SelectItem value="filename">Dateiname</SelectItem>
                    {hasAmounts && <SelectItem value="total_amount">Betrag</SelectItem>}
                    {hasDeadlines && <SelectItem value="einspruchsfrist">Einspruchsfrist</SelectItem>}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Reihenfolge</Label>
                <Select
                  value={sortOrder}
                  onValueChange={(value) => setValue('sortOrder', value as 'asc' | 'desc')}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="desc">Absteigend (neueste zuerst)</SelectItem>
                    <SelectItem value="asc">Aufsteigend (älteste zuerst)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          <DialogFooter className="flex justify-between pt-4">
            <Button
              type="button"
              variant="ghost"
              onClick={handleReset}
              className="gap-2 text-muted-foreground"
            >
              <X className="w-4 h-4" />
              Filter zurücksetzen
            </Button>

            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={handleClose}>
                Abbrechen
              </Button>
              <Button type="submit" className="gap-2">
                <Filter className="w-4 h-4" />
                Anwenden
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
