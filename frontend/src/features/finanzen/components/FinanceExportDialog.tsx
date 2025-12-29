/**
 * FinanceExportDialog - Export Dialog fuer Finanz-Dokumente
 *
 * Ermoeglicht den Export von ausgewaehlten Finanz-Dokumenten
 * in verschiedenen Formaten (JSON, CSV, ZIP, Excel, PDF).
 *
 * Features:
 * - Format-Auswahl
 * - Filter-Optionen (Text, Metadaten)
 * - Async Export mit Progress-Tracking
 * - WebSocket fuer Echtzeit-Updates
 * - Accessibility-konform (WCAG 2.1 AA)
 */

import { memo, useState, useCallback, useEffect, useRef } from 'react'
import {
  Download,
  FileJson,
  FileSpreadsheet,
  FileArchive,
  FileText,
  Loader2,
  Check,
  X,
  AlertCircle,
} from 'lucide-react'
import { apiClient } from '@/lib/api/client'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription } from '@/components/ui/alert'
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
import { useToast } from '@/components/ui/use-toast'

// ==================== TYPES ====================

interface FinanceExportDialogProps {
  isOpen: boolean
  onClose: () => void
  documentIds: string[]
  year?: string
  category?: string
}

type ExportFormat = 'json' | 'csv' | 'zip' | 'excel' | 'pdf'

type ExportStatus = 'idle' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'

interface ExportJobStatus {
  jobId: string
  status: ExportStatus
  progress: number
  totalDocuments: number
  processedDocuments: number
  failedDocuments: number
  message?: string
  downloadUrl?: string
  error?: string
}

// ==================== FORMAT CONFIG ====================

const FORMAT_CONFIG: Record<ExportFormat, {
  label: string
  description: string
  icon: typeof FileJson
  extension: string
}> = {
  json: {
    label: 'JSON',
    description: 'Strukturiertes Datenformat',
    icon: FileJson,
    extension: '.json',
  },
  csv: {
    label: 'CSV',
    description: 'Tabellenkalkulation (Excel-kompatibel)',
    icon: FileSpreadsheet,
    extension: '.csv',
  },
  excel: {
    label: 'Excel',
    description: 'Microsoft Excel Format',
    icon: FileSpreadsheet,
    extension: '.xlsx',
  },
  zip: {
    label: 'ZIP',
    description: 'Archiv mit Originaldateien',
    icon: FileArchive,
    extension: '.zip',
  },
  pdf: {
    label: 'PDF',
    description: 'Druckbares Dokument',
    icon: FileText,
    extension: '.pdf',
  },
}

// ==================== MAIN COMPONENT ====================

export const FinanceExportDialog = memo(function FinanceExportDialog({
  isOpen,
  onClose,
  documentIds,
  year,
  category,
}: FinanceExportDialogProps) {
  const [format, setFormat] = useState<ExportFormat>('csv')
  const [includeText, setIncludeText] = useState(true)
  const [includeMetadata, setIncludeMetadata] = useState(true)
  const [exportStatus, setExportStatus] = useState<ExportJobStatus | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const { toast } = useToast()

  // Reset state when dialog closes
  useEffect(() => {
    if (!isOpen) {
      setExportStatus(null)
      setIsStarting(false)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [isOpen])

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  // Start export
  const handleStartExport = useCallback(async () => {
    if (documentIds.length === 0) {
      toast({
        title: 'Keine Dokumente ausgewaehlt',
        description: 'Bitte waehlen Sie mindestens ein Dokument aus.',
        variant: 'destructive',
      })
      return
    }

    setIsStarting(true)

    try {
      const response = await apiClient.post<{
        job_id: string
        status: string
        message: string
        total_documents: number
      }>('/exports/jobs', {
        document_ids: documentIds,
        format: format,
        include_text: includeText,
        include_metadata: includeMetadata,
      })

      const jobId = response.data.job_id

      setExportStatus({
        jobId,
        status: 'queued',
        progress: 0,
        totalDocuments: response.data.total_documents,
        processedDocuments: 0,
        failedDocuments: 0,
        message: response.data.message,
      })

      // Connect WebSocket for real-time updates
      connectWebSocket(jobId)
    } catch (error) {
      toast({
        title: 'Export fehlgeschlagen',
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
        variant: 'destructive',
      })
      setExportStatus({
        jobId: '',
        status: 'failed',
        progress: 0,
        totalDocuments: documentIds.length,
        processedDocuments: 0,
        failedDocuments: 0,
        error: 'Export konnte nicht gestartet werden',
      })
    } finally {
      setIsStarting(false)
    }
  }, [documentIds, format, includeText, includeMetadata, toast])

  // WebSocket connection for progress updates
  const connectWebSocket = useCallback((jobId: string) => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/api/v1/exports/jobs/${jobId}/ws`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          setExportStatus((prev) => ({
            ...prev!,
            status: data.status || prev?.status || 'processing',
            progress: data.progress ?? prev?.progress ?? 0,
            processedDocuments: data.processed_documents ?? prev?.processedDocuments ?? 0,
            failedDocuments: data.failed_documents ?? prev?.failedDocuments ?? 0,
            message: data.message || prev?.message,
            downloadUrl: data.download_url,
            error: data.error_message,
          }))

          // Show toast on completion
          if (data.status === 'completed') {
            toast({
              title: 'Export abgeschlossen',
              description: `${data.processed_documents || 0} Dokument(e) erfolgreich exportiert.`,
            })
          } else if (data.status === 'failed') {
            toast({
              title: 'Export fehlgeschlagen',
              description: data.error_message || 'Ein Fehler ist aufgetreten.',
              variant: 'destructive',
            })
          }
        } catch {
          // Ignore parsing errors
        }
      }

      ws.onerror = () => {
        // Fallback to polling if WebSocket fails
        startPolling(jobId)
      }

      ws.onclose = () => {
        wsRef.current = null
      }
    } catch {
      // Fallback to polling
      startPolling(jobId)
    }
  }, [toast])

  // Fallback polling for progress
  const startPolling = useCallback((jobId: string) => {
    const pollInterval = setInterval(async () => {
      try {
        const response = await apiClient.get<{
          job_id: string
          status: string
          progress: number
          total_documents: number
          processed_documents: number
          failed_documents: number
          message?: string
          error_message?: string
          result_summary?: { download_url?: string }
        }>(`/exports/jobs/${jobId}`)

        const data = response.data

        setExportStatus({
          jobId: data.job_id,
          status: data.status as ExportStatus,
          progress: data.progress,
          totalDocuments: data.total_documents,
          processedDocuments: data.processed_documents,
          failedDocuments: data.failed_documents,
          message: data.message,
          downloadUrl: data.result_summary?.download_url,
          error: data.error_message,
        })

        // Stop polling when complete
        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          clearInterval(pollInterval)
        }
      } catch {
        clearInterval(pollInterval)
      }
    }, 2000)

    // Cleanup on unmount
    return () => clearInterval(pollInterval)
  }, [])

  // Cancel export
  const handleCancelExport = useCallback(async () => {
    if (!exportStatus?.jobId) return

    try {
      await apiClient.post(`/exports/jobs/${exportStatus.jobId}/cancel`)
      setExportStatus((prev) => ({
        ...prev!,
        status: 'cancelled',
        message: 'Export wurde abgebrochen',
      }))
      toast({
        title: 'Export abgebrochen',
        description: 'Der Export wurde erfolgreich abgebrochen.',
      })
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Export konnte nicht abgebrochen werden.',
        variant: 'destructive',
      })
    }
  }, [exportStatus?.jobId, toast])

  // Download result
  const handleDownload = useCallback(() => {
    if (exportStatus?.downloadUrl) {
      window.open(exportStatus.downloadUrl, '_blank')
    }
  }, [exportStatus?.downloadUrl])

  const isExporting = exportStatus && ['queued', 'processing'].includes(exportStatus.status)
  const isComplete = exportStatus?.status === 'completed'
  const isFailed = exportStatus?.status === 'failed' || exportStatus?.status === 'cancelled'

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download className="h-5 w-5" aria-hidden="true" />
            Dokumente exportieren
          </DialogTitle>
          <DialogDescription>
            {documentIds.length} Dokument{documentIds.length !== 1 ? 'e' : ''} exportieren
            {year && ` aus ${year}`}
            {category && ` (${category})`}
          </DialogDescription>
        </DialogHeader>

        {/* Export configuration (only shown before starting) */}
        {!exportStatus && (
          <div className="space-y-4 py-4">
            {/* Format selection */}
            <div className="space-y-2">
              <Label htmlFor="export-format">Format</Label>
              <Select value={format} onValueChange={(v) => setFormat(v as ExportFormat)}>
                <SelectTrigger id="export-format">
                  <SelectValue placeholder="Format waehlen" />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(FORMAT_CONFIG).map(([key, config]) => {
                    const Icon = config.icon
                    return (
                      <SelectItem key={key} value={key}>
                        <div className="flex items-center gap-2">
                          <Icon className="h-4 w-4" aria-hidden="true" />
                          <span>{config.label}</span>
                          <span className="text-xs text-muted-foreground">
                            - {config.description}
                          </span>
                        </div>
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>

            {/* Options */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="include-text">OCR-Text einschliessen</Label>
                  <p className="text-xs text-muted-foreground">
                    Extrahierter Text aus OCR
                  </p>
                </div>
                <Switch
                  id="include-text"
                  checked={includeText}
                  onCheckedChange={setIncludeText}
                />
              </div>

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="include-metadata">Metadaten einschliessen</Label>
                  <p className="text-xs text-muted-foreground">
                    Kategorie, Datum, Betraege etc.
                  </p>
                </div>
                <Switch
                  id="include-metadata"
                  checked={includeMetadata}
                  onCheckedChange={setIncludeMetadata}
                />
              </div>
            </div>
          </div>
        )}

        {/* Export progress */}
        {exportStatus && (
          <div className="space-y-4 py-4">
            {/* Status badge */}
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Status</span>
              <Badge
                variant={
                  isComplete ? 'default' :
                  isFailed ? 'destructive' :
                  'secondary'
                }
              >
                {exportStatus.status === 'queued' && 'In Warteschlange'}
                {exportStatus.status === 'processing' && 'Wird verarbeitet'}
                {exportStatus.status === 'completed' && 'Abgeschlossen'}
                {exportStatus.status === 'failed' && 'Fehlgeschlagen'}
                {exportStatus.status === 'cancelled' && 'Abgebrochen'}
              </Badge>
            </div>

            {/* Progress bar */}
            {isExporting && (
              <div className="space-y-2">
                <Progress value={exportStatus.progress} className="h-2" />
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{exportStatus.message || 'Verarbeite...'}</span>
                  <span>
                    {exportStatus.processedDocuments}/{exportStatus.totalDocuments}
                  </span>
                </div>
              </div>
            )}

            {/* Success message */}
            {isComplete && (
              <Alert>
                <Check className="h-4 w-4 text-green-600" />
                <AlertDescription>
                  Export erfolgreich! {exportStatus.processedDocuments} Dokument(e) exportiert.
                  {exportStatus.failedDocuments > 0 && (
                    <span className="text-amber-600">
                      {' '}({exportStatus.failedDocuments} fehlgeschlagen)
                    </span>
                  )}
                </AlertDescription>
              </Alert>
            )}

            {/* Error message */}
            {isFailed && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  {exportStatus.error || 'Export fehlgeschlagen'}
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}

        <DialogFooter className="gap-2">
          {/* Before export */}
          {!exportStatus && (
            <>
              <Button variant="outline" onClick={onClose}>
                Abbrechen
              </Button>
              <Button
                onClick={handleStartExport}
                disabled={isStarting || documentIds.length === 0}
              >
                {isStarting ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
                    Starte...
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4 mr-2" aria-hidden="true" />
                    Export starten
                  </>
                )}
              </Button>
            </>
          )}

          {/* During export */}
          {isExporting && (
            <Button variant="destructive" onClick={handleCancelExport}>
              <X className="h-4 w-4 mr-2" aria-hidden="true" />
              Abbrechen
            </Button>
          )}

          {/* After export */}
          {(isComplete || isFailed) && (
            <>
              <Button variant="outline" onClick={onClose}>
                Schliessen
              </Button>
              {isComplete && exportStatus?.downloadUrl && (
                <Button onClick={handleDownload}>
                  <Download className="h-4 w-4 mr-2" aria-hidden="true" />
                  Herunterladen
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
})

export default FinanceExportDialog
