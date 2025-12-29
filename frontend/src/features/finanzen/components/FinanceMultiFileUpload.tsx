/**
 * FinanceMultiFileUpload - Enhanced Multi-File Upload Component
 *
 * Features:
 * - Multi-file Drag & Drop zone
 * - Individual file progress bars
 * - File preview before upload
 * - OCR status tracking after upload
 * - Queue management
 */

import { useState, useCallback, useRef, useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useToast } from '@/components/ui/use-toast'
import {
  Upload,
  X,
  FileText,
  Image,
  File,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Eye,
  Trash2,
  Plus,
  Clock,
} from 'lucide-react'
import { financeService } from '@/lib/api/services/finance'
import { getFinanceCategoryById } from '../types'
import { cn } from '@/lib/utils'

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
const MAX_FILES = 20 // Maximum files per batch

// File upload status
type UploadStatus = 'pending' | 'uploading' | 'processing' | 'complete' | 'error'

interface FileItem {
  id: string
  file: File
  status: UploadStatus
  progress: number
  error?: string
  documentId?: string
  ocrStatus?: 'pending' | 'processing' | 'complete' | 'failed'
  previewUrl?: string
}

interface FinanceMultiFileUploadProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  yearId: string
  categoryId: string
}

export function FinanceMultiFileUpload({
  open,
  onOpenChange,
  yearId,
  categoryId,
}: FinanceMultiFileUploadProps) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [files, setFiles] = useState<FileItem[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [previewFile, setPreviewFile] = useState<FileItem | null>(null)

  const categoryInfo = getFinanceCategoryById(categoryId)

  // Generate unique ID for file tracking
  const generateFileId = () => `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

  // Validate file
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

  // Create preview URL for images
  const createPreviewUrl = (file: File): string | undefined => {
    if (file.type.startsWith('image/')) {
      return URL.createObjectURL(file)
    }
    return undefined
  }

  // Add files to queue
  const addFiles = useCallback(
    (newFiles: FileList | File[]) => {
      const fileArray = Array.from(newFiles)

      // Check max files limit
      if (files.length + fileArray.length > MAX_FILES) {
        toast({
          title: 'Zu viele Dateien',
          description: `Maximum ${MAX_FILES} Dateien pro Upload erlaubt.`,
          variant: 'destructive',
        })
        return
      }

      const validFiles: FileItem[] = []
      const errors: string[] = []

      fileArray.forEach((file) => {
        const error = validateFile(file)
        if (error) {
          errors.push(`${file.name}: ${error}`)
        } else {
          // Check for duplicates
          const isDuplicate = files.some(
            (f) => f.file.name === file.name && f.file.size === file.size
          )
          if (!isDuplicate) {
            validFiles.push({
              id: generateFileId(),
              file,
              status: 'pending',
              progress: 0,
              previewUrl: createPreviewUrl(file),
            })
          }
        }
      })

      if (errors.length > 0) {
        toast({
          title: 'Einige Dateien wurden uebersprungen',
          description: errors.slice(0, 3).join('\n') + (errors.length > 3 ? '\n...' : ''),
          variant: 'destructive',
        })
      }

      if (validFiles.length > 0) {
        setFiles((prev) => [...prev, ...validFiles])
      }
    },
    [files, toast]
  )

  // Drag & Drop handlers
  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      setIsDragging(false)

      if (e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files)
      }
    },
    [addFiles]
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
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files)
    }
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  // Remove file from queue
  const removeFile = useCallback((fileId: string) => {
    setFiles((prev) => {
      const file = prev.find((f) => f.id === fileId)
      if (file?.previewUrl) {
        URL.revokeObjectURL(file.previewUrl)
      }
      return prev.filter((f) => f.id !== fileId)
    })
  }, [])

  // Clear all files
  const clearAllFiles = useCallback(() => {
    files.forEach((f) => {
      if (f.previewUrl) {
        URL.revokeObjectURL(f.previewUrl)
      }
    })
    setFiles([])
  }, [files])

  // Upload single file
  const uploadFile = async (fileItem: FileItem): Promise<FileItem> => {
    // Update status to uploading
    setFiles((prev) =>
      prev.map((f) => (f.id === fileItem.id ? { ...f, status: 'uploading', progress: 0 } : f))
    )

    try {
      // Simulate progress updates (real progress would come from XMLHttpRequest)
      const progressInterval = setInterval(() => {
        setFiles((prev) =>
          prev.map((f) => {
            if (f.id === fileItem.id && f.progress < 90) {
              return { ...f, progress: f.progress + 10 }
            }
            return f
          })
        )
      }, 200)

      // Upload the file
      const result = await financeService.uploadDocument(yearId, categoryId, fileItem.file)

      clearInterval(progressInterval)

      // Update to complete - map processingStatus to ocrStatus
      const ocrStatusMap: Record<string, FileItem['ocrStatus']> = {
        pending: 'pending',
        processing: 'processing',
        completed: 'complete',
        failed: 'failed',
      }
      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileItem.id
            ? {
                ...f,
                status: 'complete',
                progress: 100,
                documentId: result.id,
                ocrStatus: ocrStatusMap[result.processingStatus] ?? 'pending',
              }
            : f
        )
      )

      return {
        ...fileItem,
        status: 'complete',
        progress: 100,
        documentId: result.id,
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Upload fehlgeschlagen'
      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileItem.id ? { ...f, status: 'error', progress: 0, error: errorMessage } : f
        )
      )
      return { ...fileItem, status: 'error', error: errorMessage }
    }
  }

  // Upload all pending files
  const uploadAllFiles = async () => {
    const pendingFiles = files.filter((f) => f.status === 'pending')
    if (pendingFiles.length === 0) return

    setIsUploading(true)

    let successCount = 0
    let errorCount = 0

    // Upload files sequentially to avoid overwhelming the server
    for (const fileItem of pendingFiles) {
      const result = await uploadFile(fileItem)
      if (result.status === 'complete') {
        successCount++
      } else {
        errorCount++
      }
    }

    setIsUploading(false)

    // Show summary toast
    if (successCount > 0) {
      toast({
        title: 'Upload abgeschlossen',
        description: `${successCount} Datei(en) erfolgreich hochgeladen${errorCount > 0 ? `, ${errorCount} fehlgeschlagen` : ''}.`,
        variant: errorCount > 0 ? 'default' : 'default',
      })

      // Invalidate queries to refresh the document list
      await queryClient.invalidateQueries({ queryKey: ['finance'] })
    }
  }

  // Retry failed upload
  const retryUpload = async (fileId: string) => {
    const fileItem = files.find((f) => f.id === fileId)
    if (!fileItem) return

    // Reset to pending first
    setFiles((prev) =>
      prev.map((f) =>
        f.id === fileId ? { ...f, status: 'pending', progress: 0, error: undefined } : f
      )
    )

    await uploadFile(fileItem)
  }

  // Close dialog
  const handleClose = () => {
    if (isUploading) {
      toast({
        title: 'Upload laeuft',
        description: 'Bitte warten Sie bis der Upload abgeschlossen ist.',
        variant: 'destructive',
      })
      return
    }

    // Cleanup preview URLs
    files.forEach((f) => {
      if (f.previewUrl) {
        URL.revokeObjectURL(f.previewUrl)
      }
    })

    setFiles([])
    setPreviewFile(null)
    onOpenChange(false)
  }

  // Format file size
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  // Get file icon based on type
  const getFileIcon = (file: File) => {
    if (file.type.startsWith('image/')) {
      return <Image className="w-5 h-5 text-blue-500" />
    }
    if (file.type === 'application/pdf') {
      return <FileText className="w-5 h-5 text-red-500" />
    }
    return <File className="w-5 h-5 text-gray-500" />
  }

  // Get status icon
  const getStatusIcon = (fileItem: FileItem) => {
    switch (fileItem.status) {
      case 'pending':
        return <Clock className="w-4 h-4 text-muted-foreground" />
      case 'uploading':
        return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
      case 'processing':
        return <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />
      case 'complete':
        return <CheckCircle2 className="w-4 h-4 text-green-500" />
      case 'error':
        return <XCircle className="w-4 h-4 text-destructive" />
      default:
        return null
    }
  }

  // Get OCR status badge
  const getOcrBadge = (ocrStatus?: FileItem['ocrStatus']) => {
    if (!ocrStatus) return null

    switch (ocrStatus) {
      case 'pending':
        return (
          <Badge variant="outline" className="text-xs">
            <Clock className="w-3 h-3 mr-1" />
            OCR ausstehend
          </Badge>
        )
      case 'processing':
        return (
          <Badge variant="outline" className="text-xs text-amber-600">
            <Loader2 className="w-3 h-3 mr-1 animate-spin" />
            OCR laeuft
          </Badge>
        )
      case 'complete':
        return (
          <Badge variant="outline" className="text-xs text-green-600">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            OCR fertig
          </Badge>
        )
      case 'failed':
        return (
          <Badge variant="outline" className="text-xs text-destructive">
            <AlertCircle className="w-3 h-3 mr-1" />
            OCR fehlgeschlagen
          </Badge>
        )
      default:
        return null
    }
  }

  // Compute stats
  const stats = useMemo(() => {
    return {
      total: files.length,
      pending: files.filter((f) => f.status === 'pending').length,
      uploading: files.filter((f) => f.status === 'uploading').length,
      complete: files.filter((f) => f.status === 'complete').length,
      error: files.filter((f) => f.status === 'error').length,
    }
  }, [files])

  const hasFiles = files.length > 0
  const hasPendingFiles = stats.pending > 0
  const allComplete = hasFiles && stats.complete === files.length

  return (
    <>
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="sm:max-w-[700px] max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Dokumente hochladen</DialogTitle>
            <DialogDescription>
              Laden Sie Dokumente in die Kategorie{' '}
              <span className="font-medium">{categoryInfo?.label || categoryId}</span> fuer das Jahr{' '}
              <span className="font-medium">{yearId}</span> hoch. Mehrfachauswahl moeglich.
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 min-h-0 space-y-4">
            {/* Dropzone */}
            <div
              className={cn(
                'relative border-2 border-dashed rounded-lg p-6 transition-colors',
                isDragging
                  ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950/20'
                  : 'border-muted-foreground/25 hover:border-muted-foreground/50'
              )}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={ALLOWED_EXTENSIONS.join(',')}
                onChange={handleFileInputChange}
                multiple
                className="hidden"
                id="multi-file-upload"
              />

              <label htmlFor="multi-file-upload" className="cursor-pointer block text-center">
                <Upload className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                <p className="font-medium">
                  {isDragging ? 'Dateien hier ablegen' : 'Dateien hierher ziehen oder klicken'}
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  PDF, PNG, JPG, TIFF (max. 50 MB pro Datei, max. {MAX_FILES} Dateien)
                </p>
              </label>
            </div>

            {/* File List */}
            {hasFiles && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">
                    {stats.total} Datei(en){' '}
                    {stats.complete > 0 && (
                      <span className="text-green-600">({stats.complete} fertig)</span>
                    )}
                    {stats.error > 0 && (
                      <span className="text-destructive"> ({stats.error} Fehler)</span>
                    )}
                  </span>
                  {!isUploading && hasPendingFiles && (
                    <Button variant="ghost" size="sm" onClick={clearAllFiles}>
                      <Trash2 className="w-4 h-4 mr-1" />
                      Alle entfernen
                    </Button>
                  )}
                </div>

                <ScrollArea className="h-[300px] border rounded-lg">
                  <div className="p-2 space-y-2">
                    {files.map((fileItem) => (
                      <div
                        key={fileItem.id}
                        className={cn(
                          'flex items-center gap-3 p-3 rounded-lg border bg-card',
                          fileItem.status === 'error' && 'border-destructive/50 bg-destructive/5'
                        )}
                      >
                        {/* File Icon / Preview */}
                        <div className="w-10 h-10 flex items-center justify-center rounded bg-muted overflow-hidden shrink-0">
                          {fileItem.previewUrl ? (
                            <img
                              src={fileItem.previewUrl}
                              alt={fileItem.file.name}
                              className="w-full h-full object-cover cursor-pointer"
                              onClick={() => setPreviewFile(fileItem)}
                            />
                          ) : (
                            getFileIcon(fileItem.file)
                          )}
                        </div>

                        {/* File Info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium truncate">{fileItem.file.name}</p>
                            {getStatusIcon(fileItem)}
                          </div>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span>{formatFileSize(fileItem.file.size)}</span>
                            {fileItem.status === 'complete' && getOcrBadge(fileItem.ocrStatus)}
                            {fileItem.error && (
                              <span className="text-destructive">{fileItem.error}</span>
                            )}
                          </div>

                          {/* Progress Bar */}
                          {(fileItem.status === 'uploading' ||
                            fileItem.status === 'processing') && (
                            <Progress value={fileItem.progress} className="h-1 mt-2" />
                          )}
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-1 shrink-0">
                          {fileItem.previewUrl && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => setPreviewFile(fileItem)}
                            >
                              <Eye className="w-4 h-4" />
                            </Button>
                          )}
                          {fileItem.status === 'error' && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-amber-600"
                              onClick={() => retryUpload(fileItem.id)}
                            >
                              <Plus className="w-4 h-4" />
                            </Button>
                          )}
                          {(fileItem.status === 'pending' || fileItem.status === 'error') && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => removeFile(fileItem.id)}
                            >
                              <X className="w-4 h-4" />
                            </Button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            )}
          </div>

          <DialogFooter className="pt-4 border-t">
            <Button type="button" variant="outline" onClick={handleClose} disabled={isUploading}>
              {allComplete ? 'Schliessen' : 'Abbrechen'}
            </Button>
            {hasPendingFiles && (
              <Button onClick={uploadAllFiles} disabled={isUploading} className="gap-2">
                {isUploading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {stats.uploading > 0
                      ? `Hochladen (${stats.complete}/${stats.total})...`
                      : 'Verarbeite...'}
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4" />
                    {stats.pending} Datei(en) hochladen
                  </>
                )}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Image Preview Dialog */}
      {previewFile && (
        <Dialog open={!!previewFile} onOpenChange={() => setPreviewFile(null)}>
          <DialogContent className="sm:max-w-[800px] max-h-[90vh]">
            <DialogHeader>
              <DialogTitle className="truncate">{previewFile.file.name}</DialogTitle>
              <DialogDescription>{formatFileSize(previewFile.file.size)}</DialogDescription>
            </DialogHeader>
            <div className="flex items-center justify-center p-4 bg-muted rounded-lg max-h-[60vh] overflow-auto">
              <img
                src={previewFile.previewUrl}
                alt={previewFile.file.name}
                className="max-w-full max-h-full object-contain"
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setPreviewFile(null)}>
                Schliessen
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  )
}

export default FinanceMultiFileUpload
