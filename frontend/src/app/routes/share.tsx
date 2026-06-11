/**
 * Share Target Route
 *
 * Handles files/URLs shared to the PWA via Web Share Target API.
 * Processes shared content and uploads documents automatically.
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Share2, Upload, CheckCircle2, XCircle, FileText, Link as LinkIcon } from 'lucide-react'
import { apiClient } from '@/lib/api/client'
import { logger } from '@/lib/logger'
import { toast } from 'sonner'

/**
 * Laedt Dateien ueber den generischen Upload-Endpoint hoch.
 * Hinweis: useDocumentUpload (Ablage-Workflow) ist hier ungeeignet,
 * da geteilte PWA-Dateien keinen Entity-/Ordner-Kontext haben.
 */
async function uploadDocuments(files: File[]): Promise<void> {
  for (const file of files) {
    const formData = new FormData()
    formData.append('file', file)
    await apiClient.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  }
}

export const Route = createFileRoute('/share')({
  component: ShareTargetPage,
})

interface SharedData {
  title?: string
  text?: string
  url?: string
  files?: File[]
}

function ShareTargetPage() {
  const navigate = useNavigate()
  const [sharedData, setSharedData] = useState<SharedData | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const isUploading = uploadStatus === 'uploading'

  // Parse shared data from URL or FormData on mount
  useEffect(() => {
    const parseSharedData = async () => {
      const url = new URL(window.location.href)
      const searchParams = url.searchParams

      // Get text/url data from query params
      const title = searchParams.get('title') || undefined
      const text = searchParams.get('text') || undefined
      const sharedUrl = searchParams.get('url') || undefined

      // Check if there are files in the POST data (for multipart form submissions)
      // Note: Files are handled by the service worker and cached
      const files: File[] = []

      // Try to get files from the cache (set by service worker)
      try {
        if ('caches' in window) {
          const cache = await caches.open('share-target-cache')
          const cachedResponse = await cache.match('/share-target-files')

          if (cachedResponse) {
            const formData = await cachedResponse.formData()
            const sharedFiles = formData.getAll('files') as File[]
            files.push(...sharedFiles)

            // Clear the cache after reading
            await cache.delete('/share-target-files')
          }
        }
      } catch (error) {
        logger.warn('[ShareTarget] Cache-Zugriff fehlgeschlagen', { error })
      }

      // Set parsed data
      const data: SharedData = {
        title,
        text,
        url: sharedUrl,
        files: files.length > 0 ? files : undefined,
      }

      if (title || text || sharedUrl || files.length > 0) {
        setSharedData(data)
        logger.info('[ShareTarget] Daten empfangen', {
          hasTitle: !!title,
          hasText: !!text,
          hasUrl: !!sharedUrl,
          fileCount: files.length,
        })
      } else {
        // No shared data - redirect to upload page
        logger.info('[ShareTarget] Keine geteilten Daten - weiterleiten')
        navigate({ to: '/upload' })
      }
    }

    parseSharedData()
  }, [navigate])

  // Handle file upload
  const handleUpload = async () => {
    if (!sharedData?.files || sharedData.files.length === 0) {
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

      await uploadDocuments(sharedData.files)

      clearInterval(progressInterval)
      setUploadProgress(100)
      setUploadStatus('success')

      toast.success('Dokumente erfolgreich hochgeladen', {
        description: `${sharedData.files.length} Datei(en) verarbeitet`,
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

  // Handle URL/text share (create note or bookmark)
  const handleSaveLink = async () => {
    const linkData = {
      url: sharedData?.url,
      text: sharedData?.text,
      title: sharedData?.title || 'Geteilter Link',
      savedAt: new Date().toISOString(),
    }

    // Speichere im LocalStorage (FUTURE: Backend API für Bookmarks)
    try {
      const existingLinks = JSON.parse(localStorage.getItem('savedLinks') || '[]')
      existingLinks.unshift(linkData)
      // Max 50 Links speichern
      localStorage.setItem('savedLinks', JSON.stringify(existingLinks.slice(0, 50)))

      toast.success('Link gespeichert', {
        description: `"${linkData.title}" wurde zu Ihren Links hinzugefügt`,
      })
    } catch {
      toast.error('Speichern fehlgeschlagen')
    }

    navigate({ to: '/' })
  }

  // Cancel and go back
  const handleCancel = () => {
    navigate({ to: '/' })
  }

  // Loading state
  if (!sharedData) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <Share2 className="mx-auto h-12 w-12 animate-pulse text-muted-foreground" />
          <p className="mt-4 text-muted-foreground">Geteilte Inhalte werden verarbeitet...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto max-w-lg px-4 py-8">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Share2 className="h-5 w-5" />
            Geteilte Inhalte
          </CardTitle>
          <CardDescription>
            Inhalte wurden mit dem Ablage-System geteilt
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Shared files */}
          {sharedData.files && sharedData.files.length > 0 && (
            <div className="space-y-3">
              <h3 className="font-medium flex items-center gap-2">
                <FileText className="h-4 w-4" />
                {sharedData.files.length} Datei(en)
              </h3>
              <ul className="space-y-2">
                {sharedData.files.map((file, index) => (
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
                  Dokumente hochladen
                </Button>
              )}
            </div>
          )}

          {/* Shared URL */}
          {sharedData.url && (
            <div className="space-y-3">
              <h3 className="font-medium flex items-center gap-2">
                <LinkIcon className="h-4 w-4" />
                Link
              </h3>
              <p className="text-sm text-muted-foreground break-all bg-muted/50 px-3 py-2 rounded">
                {sharedData.url}
              </p>
              <Button onClick={handleSaveLink} variant="secondary" className="w-full">
                Link speichern
              </Button>
            </div>
          )}

          {/* Shared text */}
          {sharedData.text && !sharedData.url && (
            <div className="space-y-3">
              <h3 className="font-medium">Text</h3>
              <p className="text-sm text-muted-foreground bg-muted/50 px-3 py-2 rounded">
                {sharedData.text}
              </p>
            </div>
          )}

          {/* Title */}
          {sharedData.title && (
            <div className="space-y-1">
              <h3 className="font-medium">Titel</h3>
              <p className="text-sm text-muted-foreground">{sharedData.title}</p>
            </div>
          )}

          {/* Cancel button */}
          <Button variant="outline" onClick={handleCancel} className="w-full">
            Abbrechen
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
