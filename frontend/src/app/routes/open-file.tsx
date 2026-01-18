/**
 * File Handler Route
 *
 * Handles files opened directly with the PWA via the File Handling API.
 * When users double-click a file type registered in the manifest (PDF, PNG, JPG, TIFF),
 * the PWA opens and this route receives the file for processing.
 *
 * @see https://developer.mozilla.org/en-US/docs/Web/API/File_Handling_API
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { FileInput, Upload, CheckCircle2, XCircle, FileText, AlertCircle } from 'lucide-react'
import { useDocumentUpload } from '@/features/ablage/hooks/use-document-upload'
import { logger } from '@/lib/logger'
import { toast } from 'sonner'

export const Route = createFileRoute('/open-file')({
  component: OpenFilePage,
})

interface FileHandlerData {
  files: File[]
  source: 'launchQueue' | 'cache' | 'manual'
}

function OpenFilePage() {
  const navigate = useNavigate()
  const [fileData, setFileData] = useState<FileHandlerData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const { uploadDocuments, isUploading } = useDocumentUpload()

  // Handle files from File Handling API on mount
  useEffect(() => {
    const handleLaunchQueue = async () => {
      setIsLoading(true)
      const files: File[] = []

      try {
        // Check if launchQueue is available (File Handling API)
        if ('launchQueue' in window) {
          const launchQueue = (window as any).launchQueue

          launchQueue.setConsumer(async (launchParams: any) => {
            if (!launchParams.files || launchParams.files.length === 0) {
              logger.info('[OpenFile] Keine Dateien in launchQueue')
              setIsLoading(false)
              return
            }

            // Get file handles and read files
            for (const fileHandle of launchParams.files) {
              try {
                const file = await fileHandle.getFile()
                files.push(file)
                logger.info('[OpenFile] Datei aus launchQueue geladen', {
                  name: file.name,
                  size: file.size,
                  type: file.type,
                })
              } catch (error) {
                logger.error('[OpenFile] Fehler beim Laden der Datei', { error })
              }
            }

            if (files.length > 0) {
              setFileData({ files, source: 'launchQueue' })
            }
            setIsLoading(false)
          })
        } else {
          // File Handling API not supported
          logger.warn('[OpenFile] File Handling API nicht unterstuetzt')

          // Try to get files from cache (fallback for older browsers)
          if ('caches' in window) {
            try {
              const cache = await caches.open('open-file-cache')
              const cachedResponse = await cache.match('/open-file-data')

              if (cachedResponse) {
                const formData = await cachedResponse.formData()
                const cachedFiles = formData.getAll('files') as File[]

                if (cachedFiles.length > 0) {
                  files.push(...cachedFiles)
                  setFileData({ files, source: 'cache' })
                }

                // Clear cache
                await cache.delete('/open-file-data')
              }
            } catch (cacheError) {
              logger.warn('[OpenFile] Cache-Zugriff fehlgeschlagen', { error: cacheError })
            }
          }

          setIsLoading(false)
        }
      } catch (error) {
        logger.error('[OpenFile] Fehler beim Verarbeiten der Dateien', { error })
        setIsLoading(false)
      }
    }

    handleLaunchQueue()
  }, [])

  // Handle file upload
  const handleUpload = async () => {
    if (!fileData?.files || fileData.files.length === 0) {
      toast.error('Keine Dateien zum Hochladen')
      return
    }

    setUploadStatus('uploading')
    setUploadProgress(10)

    try {
      // Simulate progress updates
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => Math.min(prev + 10, 90))
      }, 500)

      await uploadDocuments(fileData.files)

      clearInterval(progressInterval)
      setUploadProgress(100)
      setUploadStatus('success')

      toast.success('Dokumente erfolgreich hochgeladen', {
        description: `${fileData.files.length} Datei(en) verarbeitet`,
      })

      // Redirect to documents after short delay
      setTimeout(() => {
        navigate({ to: '/' })
      }, 2000)
    } catch (error) {
      setUploadStatus('error')
      setErrorMessage(error instanceof Error ? error.message : 'Unbekannter Fehler')
      toast.error('Upload fehlgeschlagen')
    }
  }

  // Manual file selection fallback
  const handleManualSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = event.target.files
    if (selectedFiles && selectedFiles.length > 0) {
      setFileData({
        files: Array.from(selectedFiles),
        source: 'manual',
      })
    }
  }

  // Cancel and go back
  const handleCancel = () => {
    navigate({ to: '/' })
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <FileInput className="mx-auto h-12 w-12 animate-pulse text-muted-foreground" />
          <p className="mt-4 text-muted-foreground">Datei wird geladen...</p>
        </div>
      </div>
    )
  }

  // No files state - show manual selection
  if (!fileData || fileData.files.length === 0) {
    return (
      <div className="container mx-auto max-w-lg px-4 py-8">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileInput className="h-5 w-5" />
              Datei oeffnen
            </CardTitle>
            <CardDescription>
              Keine Datei gefunden. Waehlen Sie eine Datei manuell aus.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 dark:bg-amber-950 px-3 py-2 rounded">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <p>
                Die File Handling API wird moeglicherweise nicht von Ihrem Browser unterstuetzt,
                oder die Datei konnte nicht geladen werden.
              </p>
            </div>

            {/* Manual file input */}
            <div className="space-y-3">
              <label
                htmlFor="file-input"
                className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-lg cursor-pointer hover:bg-muted/50 transition-colors"
              >
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  <Upload className="h-8 w-8 mb-2 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
                    Klicken Sie hier, um eine Datei auszuwaehlen
                  </p>
                </div>
                <input
                  id="file-input"
                  type="file"
                  className="hidden"
                  accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,application/pdf,image/png,image/jpeg,image/tiff"
                  multiple
                  onChange={handleManualSelect}
                />
              </label>
            </div>

            <Button variant="outline" onClick={handleCancel} className="w-full">
              Abbrechen
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="container mx-auto max-w-lg px-4 py-8">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileInput className="h-5 w-5" />
            Datei oeffnen
          </CardTitle>
          <CardDescription>
            {fileData.source === 'launchQueue'
              ? 'Datei wurde mit dem Ablage-System geoeffnet'
              : fileData.source === 'cache'
                ? 'Datei aus Cache geladen'
                : 'Datei manuell ausgewaehlt'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* File list */}
          <div className="space-y-3">
            <h3 className="font-medium flex items-center gap-2">
              <FileText className="h-4 w-4" />
              {fileData.files.length} Datei(en)
            </h3>
            <ul className="space-y-2">
              {fileData.files.map((file, index) => (
                <li
                  key={index}
                  className="flex items-center gap-2 text-sm text-muted-foreground bg-muted/50 px-3 py-2 rounded"
                >
                  <FileText className="h-4 w-4 flex-shrink-0" />
                  <span className="truncate">{file.name}</span>
                  <span className="ml-auto text-xs">
                    {(file.size / 1024).toFixed(1)} KB
                  </span>
                </li>
              ))}
            </ul>

            {/* Upload progress */}
            {uploadStatus !== 'idle' && (
              <div className="space-y-2">
                <Progress value={uploadProgress} />
                <p className="text-sm text-center">
                  {uploadStatus === 'uploading' && 'Wird hochgeladen...'}
                  {uploadStatus === 'success' && (
                    <span className="text-green-600 flex items-center justify-center gap-1">
                      <CheckCircle2 className="h-4 w-4" />
                      Erfolgreich hochgeladen
                    </span>
                  )}
                  {uploadStatus === 'error' && (
                    <span className="text-red-600 flex items-center justify-center gap-1">
                      <XCircle className="h-4 w-4" />
                      {errorMessage}
                    </span>
                  )}
                </p>
              </div>
            )}

            {/* Upload button */}
            {uploadStatus === 'idle' && (
              <Button
                onClick={handleUpload}
                disabled={isUploading}
                className="w-full"
              >
                <Upload className="h-4 w-4 mr-2" />
                Dokument hochladen
              </Button>
            )}
          </div>

          {/* Cancel button */}
          <Button variant="outline" onClick={handleCancel} className="w-full">
            Abbrechen
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
