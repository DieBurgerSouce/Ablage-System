/**
 * ImportUploadZone - Dual File Upload fuer Lexware Excel-Dateien
 *
 * WICHTIG: Backend erwartet ZWEI Dateien gleichzeitig (Folie + Messer)!
 *
 * Features:
 * - Separate Upload-Zonen fuer Folie und Messer
 * - File Validation (.xlsx, .xls)
 * - File Preview mit Groessenangabe
 * - Beide Dateien muessen ausgewaehlt sein vor Import
 */

import { useCallback, useState, useId } from 'react'
import { Upload, FileSpreadsheet, X, AlertCircle, CheckCircle2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface ImportUploadZoneProps {
  folieFile: File | null
  messerFile: File | null
  onFolieFileSelect: (file: File | null) => void
  onMesserFileSelect: (file: File | null) => void
  entityType: 'customer' | 'supplier'
  isDisabled?: boolean
}

const ACCEPTED_EXTENSIONS = ['.xlsx', '.xls']
const ACCEPTED_MIME_TYPES = [
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
]

export function ImportUploadZone({
  folieFile,
  messerFile,
  onFolieFileSelect,
  onMesserFileSelect,
  entityType,
  isDisabled = false,
}: ImportUploadZoneProps) {
  const [folieError, setFolieError] = useState<string | null>(null)
  const [messerError, setMesserError] = useState<string | null>(null)

  const folieInputId = useId()
  const messerInputId = useId()

  const validateFile = (file: File, setError: (e: string | null) => void): boolean => {
    setError(null)

    const extension = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!ACCEPTED_EXTENSIONS.includes(extension)) {
      setError(`Ungueltiges Dateiformat. Erlaubt: ${ACCEPTED_EXTENSIONS.join(', ')}`)
      return false
    }

    if (file.type && !ACCEPTED_MIME_TYPES.includes(file.type)) {
      setError('Ungueltiger Dateityp. Bitte eine Excel-Datei waehlen.')
      return false
    }

    const maxSize = 50 * 1024 * 1024
    if (file.size > maxSize) {
      setError('Datei zu gross. Maximum: 50 MB')
      return false
    }

    return true
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const entityLabel = entityType === 'customer' ? 'Kunden' : 'Lieferanten'
  const bothFilesSelected = folieFile !== null && messerFile !== null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Upload className="h-5 w-5" />
          Excel-Dateien hochladen
        </CardTitle>
        <CardDescription>
          Lexware {entityLabel}-Export als Excel-Dateien (.xlsx, .xls) -
          <strong className="text-foreground"> Beide Firmen erforderlich</strong>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Status Banner */}
        {bothFilesSelected ? (
          <div className="flex items-center gap-2 p-3 bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-lg text-green-700 dark:text-green-300">
            <CheckCircle2 className="h-5 w-5 flex-shrink-0" />
            <span className="font-medium">Beide Dateien ausgewaehlt - Bereit zum Import</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 p-3 bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800 rounded-lg text-yellow-700 dark:text-yellow-300">
            <AlertCircle className="h-5 w-5 flex-shrink-0" />
            <span>Bitte waehlen Sie beide Dateien aus (Folie + Messer)</span>
          </div>
        )}

        {/* Two Upload Zones */}
        <div className="grid md:grid-cols-2 gap-4">
          {/* Folie Upload */}
          <SingleFileUpload
            label="Spargel Folie GmbH"
            file={folieFile}
            error={folieError}
            inputId={folieInputId}
            isDisabled={isDisabled}
            onFileSelect={(file) => {
              if (file && validateFile(file, setFolieError)) {
                onFolieFileSelect(file)
              } else if (!file) {
                onFolieFileSelect(null)
                setFolieError(null)
              }
            }}
            formatFileSize={formatFileSize}
            entityLabel={entityLabel}
          />

          {/* Messer Upload */}
          <SingleFileUpload
            label="Spargel Messer GmbH"
            file={messerFile}
            error={messerError}
            inputId={messerInputId}
            isDisabled={isDisabled}
            onFileSelect={(file) => {
              if (file && validateFile(file, setMesserError)) {
                onMesserFileSelect(file)
              } else if (!file) {
                onMesserFileSelect(null)
                setMesserError(null)
              }
            }}
            formatFileSize={formatFileSize}
            entityLabel={entityLabel}
          />
        </div>
      </CardContent>
    </Card>
  )
}

interface SingleFileUploadProps {
  label: string
  file: File | null
  error: string | null
  inputId: string
  isDisabled: boolean
  onFileSelect: (file: File | null) => void
  formatFileSize: (bytes: number) => string
  entityLabel: string
}

function SingleFileUpload({
  label,
  file,
  error,
  inputId,
  isDisabled,
  onFileSelect,
  formatFileSize,
  entityLabel,
}: SingleFileUploadProps) {
  const [isDragging, setIsDragging] = useState(false)

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      setIsDragging(false)
      if (isDisabled) return
      const droppedFile = e.dataTransfer.files?.[0]
      if (droppedFile) {
        onFileSelect(droppedFile)
      }
    },
    [isDisabled, onFileSelect]
  )

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFile = e.target.files?.[0]
      if (selectedFile) {
        onFileSelect(selectedFile)
      }
    },
    [onFileSelect]
  )

  const handleClick = useCallback(() => {
    if (!isDisabled) {
      document.getElementById(inputId)?.click()
    }
  }, [isDisabled, inputId])

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">{label}</label>
      <div
        className={cn(
          'border-2 border-dashed rounded-lg p-6 text-center transition-all cursor-pointer',
          isDragging && 'border-primary bg-primary/5',
          !isDragging && !file && 'hover:border-primary/50',
          file && 'border-green-500 bg-green-50 dark:bg-green-950/20',
          isDisabled && 'opacity-50 cursor-not-allowed'
        )}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={handleClick}
        role="button"
        tabIndex={isDisabled ? -1 : 0}
        aria-label={`${label} Excel-Datei hochladen`}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            handleClick()
          }
        }}
      >
        <input
          id={inputId}
          type="file"
          className="hidden"
          accept=".xlsx,.xls"
          onChange={handleInputChange}
          disabled={isDisabled}
        />

        {file ? (
          <div className="flex flex-col items-center gap-2">
            <FileSpreadsheet className="h-8 w-8 text-green-600 dark:text-green-400" />
            <div>
              <p className="font-medium text-green-800 dark:text-green-200 text-sm truncate max-w-[200px]">
                {file.name}
              </p>
              <p className="text-xs text-green-600 dark:text-green-400">
                {formatFileSize(file.size)}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                onFileSelect(null)
              }}
              disabled={isDisabled}
            >
              <X className="h-3 w-3 mr-1" />
              Entfernen
            </Button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <Upload className="h-8 w-8 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">
                Datei waehlen
              </p>
              <p className="text-xs text-muted-foreground">
                {entityLabel}-Export
              </p>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 p-2 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded text-red-700 dark:text-red-300">
          <AlertCircle className="h-3 w-3 flex-shrink-0" />
          <span className="text-xs">{error}</span>
        </div>
      )}
    </div>
  )
}
