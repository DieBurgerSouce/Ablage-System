/**
 * Document Upload Hook
 *
 * Provides document upload functionality via API.
 */

import { useState } from 'react'
import { apiClient } from '@/lib/api/client'
import { logger } from '@/lib/logger'

interface UseDocumentUploadReturn {
  uploadDocuments: (files: File[]) => Promise<void>
  isUploading: boolean
  error: string | null
}

export function useDocumentUpload(): UseDocumentUploadReturn {
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const uploadDocuments = async (files: File[]): Promise<void> => {
    if (files.length === 0) {
      throw new Error('Keine Dateien zum Hochladen')
    }

    setIsUploading(true)
    setError(null)

    try {
      // Upload files one by one or as batch
      for (const file of files) {
        const formData = new FormData()
        formData.append('file', file)

        logger.info('[DocumentUpload] Uploading file', {
          name: file.name,
          size: file.size,
          type: file.type
        })

        await apiClient.post('/documents/upload', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        })

        logger.info('[DocumentUpload] File uploaded successfully', { name: file.name })
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Upload fehlgeschlagen'
      setError(errorMessage)
      logger.error('[DocumentUpload] Upload failed', { error: err })
      throw err
    } finally {
      setIsUploading(false)
    }
  }

  return {
    uploadDocuments,
    isUploading,
    error,
  }
}
