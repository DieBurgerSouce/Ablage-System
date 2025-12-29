/**
 * FinanceDocumentUploadDialog
 *
 * Dialog zum Hochladen von Finanz-Dokumenten mit optionalen Metadaten.
 * Unterstuetzt Drag & Drop sowie manuelle Dateiauswahl.
 */

import { useState, useCallback, useRef } from 'react'
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
import { Checkbox } from '@/components/ui/checkbox'
import { useToast } from '@/components/ui/use-toast'
import { Upload, X, FileText, Loader2 } from 'lucide-react'
import { useUploadFinanceDocument } from '../hooks/use-finanzen-queries'
import { getFinanceCategoryById, categoryHasDeadlines, categoryHasAmounts } from '../types'
import type { FinanceDocumentUploadMetadata } from '@/lib/api/services/finance'

// Erlaubte Dateitypen
const ALLOWED_FILE_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/tiff',
  'image/webp',
]

const ALLOWED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.webp']

const MAX_FILE_SIZE = 50 * 1024 * 1024 // 50 MB

interface FinanceDocumentUploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  yearId: string
  categoryId: string
}

interface FormData {
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
  skipOcr: boolean
}

export function FinanceDocumentUploadDialog({
  open,
  onOpenChange,
  yearId,
  categoryId,
}: FinanceDocumentUploadDialogProps) {
  const { toast } = useToast()
  const uploadMutation = useUploadFinanceDocument()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const categoryInfo = getFinanceCategoryById(categoryId)
  const hasAmounts = categoryHasAmounts(categoryId)
  const hasDeadlines = categoryHasDeadlines(categoryId)

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { isSubmitting },
  } = useForm<FormData>({
    defaultValues: {
      documentDate: '',
      totalAmount: '',
      nachzahlung: '',
      erstattung: '',
      einspruchsfrist: '',
      aktenzeichen: '',
      steuernummer: '',
      finanzamt: '',
      steuerart: '',
      zeitraum: '',
      versicherungsnummer: '',
      vertragsnummer: '',
      skipOcr: false,
    },
  })

  const skipOcr = watch('skipOcr')
  const steuerart = watch('steuerart')

  const validateFile = (file: File): string | null => {
    if (!ALLOWED_FILE_TYPES.includes(file.type)) {
      const ext = file.name.split('.').pop()?.toLowerCase()
      if (!ext || !ALLOWED_EXTENSIONS.some((e) => e === `.${ext}`)) {
        return `Dateityp nicht erlaubt. Erlaubte Typen: ${ALLOWED_EXTENSIONS.join(', ')}`
      }
    }

    if (file.size > MAX_FILE_SIZE) {
      return `Datei zu gross. Maximum: ${MAX_FILE_SIZE / 1024 / 1024} MB`
    }

    return null
  }

  const handleFileSelect = useCallback((file: File) => {
    const error = validateFile(file)
    if (error) {
      toast({
        title: 'Dateifehler',
        description: error,
        variant: 'destructive',
      })
      return
    }
    setSelectedFile(file)
  }, [toast])

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      setIsDragging(false)

      const file = e.dataTransfer.files[0]
      if (file) {
        handleFileSelect(file)
      }
    },
    [handleFileSelect]
  )

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      handleFileSelect(file)
    }
  }

  const removeFile = () => {
    setSelectedFile(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const onSubmit = async (data: FormData) => {
    if (!selectedFile) {
      toast({
        title: 'Keine Datei',
        description: 'Bitte waehlen Sie eine Datei zum Hochladen aus.',
        variant: 'destructive',
      })
      return
    }

    try {
      const metadata: FinanceDocumentUploadMetadata = {}

      if (data.documentDate) metadata.documentDate = data.documentDate
      if (data.totalAmount) metadata.totalAmount = parseFloat(data.totalAmount)
      if (data.nachzahlung) metadata.nachzahlung = parseFloat(data.nachzahlung)
      if (data.erstattung) metadata.erstattung = parseFloat(data.erstattung)
      if (data.einspruchsfrist) metadata.einspruchsfrist = data.einspruchsfrist
      if (data.aktenzeichen) metadata.aktenzeichen = data.aktenzeichen
      if (data.steuernummer) metadata.steuernummer = data.steuernummer
      if (data.finanzamt) metadata.finanzamt = data.finanzamt
      if (data.steuerart) metadata.steuerart = data.steuerart
      if (data.zeitraum) metadata.zeitraum = data.zeitraum
      if (data.versicherungsnummer) metadata.versicherungsnummer = data.versicherungsnummer
      if (data.vertragsnummer) metadata.vertragsnummer = data.vertragsnummer
      if (data.skipOcr) metadata.skipOcr = true

      await uploadMutation.mutateAsync({
        year: yearId,
        category: categoryId,
        file: selectedFile,
        metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
      })

      toast({
        title: 'Dokument hochgeladen',
        description: `${selectedFile.name} wurde erfolgreich hochgeladen.`,
      })

      // Reset and close
      reset()
      setSelectedFile(null)
      setShowAdvanced(false)
      onOpenChange(false)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unbekannter Fehler'
      toast({
        title: 'Fehler beim Hochladen',
        description: errorMessage,
        variant: 'destructive',
      })
    }
  }

  const handleClose = () => {
    reset()
    setSelectedFile(null)
    setShowAdvanced(false)
    onOpenChange(false)
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Dokument hochladen</DialogTitle>
          <DialogDescription>
            Laden Sie ein Dokument in die Kategorie{' '}
            <span className="font-medium">{categoryInfo?.label || categoryId}</span> fuer das Jahr{' '}
            <span className="font-medium">{yearId}</span> hoch.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Dropzone */}
          <div
            className={`relative border-2 border-dashed rounded-lg p-6 transition-colors ${
              isDragging
                ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950/20'
                : selectedFile
                  ? 'border-emerald-300 bg-emerald-50/50 dark:bg-emerald-950/10'
                  : 'border-muted-foreground/25 hover:border-muted-foreground/50'
            }`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ALLOWED_EXTENSIONS.join(',')}
              onChange={handleFileInputChange}
              className="hidden"
              id="file-upload"
            />

            {selectedFile ? (
              <div className="flex items-center gap-4">
                <div className="p-3 bg-emerald-100 dark:bg-emerald-900 rounded-lg">
                  <FileText className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{selectedFile.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {formatFileSize(selectedFile.size)}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={removeFile}
                  className="shrink-0"
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>
            ) : (
              <label htmlFor="file-upload" className="cursor-pointer block text-center">
                <Upload className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                <p className="font-medium">Datei hierher ziehen oder klicken</p>
                <p className="text-sm text-muted-foreground mt-1">
                  PDF, PNG, JPG, TIFF (max. 50 MB)
                </p>
              </label>
            )}
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

          {/* Erweiterte Optionen Toggle */}
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            {showAdvanced ? '- Erweiterte Optionen ausblenden' : '+ Erweiterte Optionen anzeigen'}
          </button>

          {/* Erweiterte Optionen */}
          {showAdvanced && (
            <div className="space-y-4 border-t pt-4">
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
                      <SelectValue placeholder="Steuerart waehlen" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="einkommensteuer">Einkommensteuer</SelectItem>
                      <SelectItem value="koerperschaftsteuer">Koerperschaftsteuer</SelectItem>
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
                  <Input id="zeitraum" placeholder="z.B. 2024 oder Q1/2024" {...register('zeitraum')} />
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

              <div className="flex items-center gap-2 pt-2">
                <Checkbox
                  id="skipOcr"
                  checked={skipOcr}
                  onCheckedChange={(checked) => setValue('skipOcr', checked === true)}
                />
                <Label htmlFor="skipOcr" className="text-sm">
                  OCR-Verarbeitung ueberspringen (manuelle Dateneingabe)
                </Label>
              </div>
            </div>
          )}

          <DialogFooter className="pt-4">
            <Button type="button" variant="outline" onClick={handleClose}>
              Abbrechen
            </Button>
            <Button
              type="submit"
              disabled={!selectedFile || isSubmitting || uploadMutation.isPending}
              className="gap-2"
            >
              {(isSubmitting || uploadMutation.isPending) && (
                <Loader2 className="w-4 h-4 animate-spin" />
              )}
              {isSubmitting || uploadMutation.isPending ? 'Hochladen...' : 'Hochladen'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
