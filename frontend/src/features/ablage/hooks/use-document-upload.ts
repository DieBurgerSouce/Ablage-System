/**
 * Document Upload Hook - Enterprise OCR Workflow
 *
 * Orchestriert den gesamten Upload-Flow:
 * 1. Datei hochladen + OCR
 * 2. Quick Classification
 * 3. Review im Modal (mit Rename-Vorschlag)
 * 4. Finales Speichern via upload-complete
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { logger } from '@/lib/logger'
import type {
  OCRProcessResult,
  UploadCompleteRequest,
  UploadCompleteResponse,
  UploadWorkflowStatus,
  UploadWorkflowState,
  UseDocumentUploadOptions,
} from '../types'
import {
  processDocumentOCR,
  uploadComplete,
  extendTempFileTTL,
} from '../api/ablage-api'

// TTL-Verlängerung alle 20 Minuten, wenn User im Review-Modal ist
const TTL_EXTEND_INTERVAL_MS = 20 * 60 * 1000

interface UseDocumentUploadReturn {
  // State
  state: UploadWorkflowState

  // Actions
  startUpload: (file: File) => Promise<void>
  saveDocument: (data: Partial<UploadCompleteRequest>) => Promise<UploadCompleteResponse>
  cancel: () => void
  reset: () => void

  // Convenience
  isProcessing: boolean
  isReviewReady: boolean
  isSaving: boolean
  hasError: boolean
}

const initialState: UploadWorkflowState = {
  status: 'idle',
  progress: 0,
  file: null,
  fileUrl: null,
  tempFileId: null,
  ocrResult: null,
  quickClassification: null,
  renameSuggestion: null,
  error: null,
}

export function useDocumentUpload(
  options: UseDocumentUploadOptions
): UseDocumentUploadReturn {
  const [state, setState] = useState<UploadWorkflowState>(initialState)
  const queryClient = useQueryClient()
  const ttlExtendInterval = useRef<NodeJS.Timeout | null>(null)
  const abortController = useRef<AbortController | null>(null)

  // Cleanup TTL-Extend Interval on unmount
  useEffect(() => {
    return () => {
      if (ttlExtendInterval.current) {
        clearInterval(ttlExtendInterval.current)
      }
      if (abortController.current) {
        abortController.current.abort()
      }
    }
  }, [])

  // TTL-Verlängerung starten wenn im Review-Status
  useEffect(() => {
    if (state.status === 'review' && state.tempFileId) {
      // Starte Interval für TTL-Verlängerung
      ttlExtendInterval.current = setInterval(async () => {
        if (state.tempFileId) {
          const success = await extendTempFileTTL(state.tempFileId)
          if (success) {
            logger.debug('[DocumentUpload] TTL extended', { tempFileId: state.tempFileId })
          }
        }
      }, TTL_EXTEND_INTERVAL_MS)

      return () => {
        if (ttlExtendInterval.current) {
          clearInterval(ttlExtendInterval.current)
          ttlExtendInterval.current = null
        }
      }
    }
  }, [state.status, state.tempFileId])

  /**
   * Startet den Upload + OCR + Quick Classification Workflow
   */
  const startUpload = useCallback(async (file: File) => {
    // Cleanup previous state
    if (state.fileUrl) {
      URL.revokeObjectURL(state.fileUrl)
    }

    // Reset and set uploading
    setState({
      ...initialState,
      status: 'uploading',
      file,
      progress: 0,
    })

    abortController.current = new AbortController()

    try {
      logger.info('[DocumentUpload] Starting upload', {
        name: file.name,
        size: file.size,
        type: file.type,
      })

      // Update status to processing after upload starts
      const onProgress = (progress: number) => {
        setState(prev => {
          // Switch to 'processing' when upload complete
          if (progress >= 100 && prev.status === 'uploading') {
            return { ...prev, status: 'processing', progress }
          }
          return { ...prev, progress }
        })
      }

      // Call OCR API
      const result = await processDocumentOCR(
        file,
        options.ocrBackend || 'deepseek',
        onProgress
      )

      // Check if cancelled
      if (abortController.current?.signal.aborted) {
        logger.info('[DocumentUpload] Upload cancelled')
        return
      }

      // Create preview URL
      const fileUrl = URL.createObjectURL(file)

      logger.info('[DocumentUpload] OCR completed', {
        success: result.success,
        confidence: result.confidence,
        hasQuickClassification: !!result.quickClassification,
        hasRenameSuggestion: !!result.renameSuggestion,
      })

      // Set review state
      setState(prev => ({
        ...prev,
        status: 'review',
        progress: 100,
        fileUrl,
        tempFileId: result.tempFileId,
        ocrResult: {
          text: result.text,
          confidence: result.confidence,
          pageCount: result.pageCount,
        },
        quickClassification: result.quickClassification,
        renameSuggestion: result.renameSuggestion,
      }))

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler'
      logger.error('[DocumentUpload] Upload failed', { error })

      setState(prev => ({
        ...prev,
        status: 'error',
        error: errorMessage,
      }))

      throw error
    }
  }, [state.fileUrl, options.ocrBackend])

  /**
   * Speichert das Dokument endgültig nach Review
   */
  const saveDocument = useCallback(async (
    data: Partial<UploadCompleteRequest>
  ): Promise<UploadCompleteResponse> => {
    if (!state.tempFileId) {
      throw new Error('Keine temporäre Datei vorhanden')
    }

    setState(prev => ({ ...prev, status: 'saving' }))

    try {
      // Build complete request
      const request: UploadCompleteRequest = {
        tempFileId: state.tempFileId,
        finalFilename: data.finalFilename || state.file?.name || 'dokument.pdf',
        documentType: data.documentType || state.quickClassification?.suggestedDocumentType || 'document',
        documentNumber: data.documentNumber || state.quickClassification?.extractedData?.documentNumber || null,
        documentDate: data.documentDate || state.quickClassification?.extractedData?.documentDate || null,
        totalAmount: data.totalAmount ?? state.quickClassification?.extractedData?.totalAmount ?? null,
        currency: data.currency || state.quickClassification?.extractedData?.currency || 'EUR',
        dueDate: data.dueDate || state.quickClassification?.extractedData?.dueDate || null,
        businessEntityId: data.businessEntityId || state.quickClassification?.matchedEntityId || options.entityId || null,
        folderId: data.folderId || options.folderId,
        category: data.category || options.category,
        entityType: data.entityType || options.entityType,
        tags: data.tags || state.quickClassification?.suggestedTags || [],
        ocrText: state.ocrResult?.text || null,
        ocrConfidence: state.ocrResult?.confidence || null,
      }

      logger.info('[DocumentUpload] Saving document', {
        tempFileId: request.tempFileId,
        finalFilename: request.finalFilename,
        category: request.category,
      })

      const response = await uploadComplete(request)

      logger.info('[DocumentUpload] Document saved', {
        documentId: response.documentId,
        storagePath: response.storagePath,
      })

      // Cleanup
      if (state.fileUrl) {
        URL.revokeObjectURL(state.fileUrl)
      }

      // Invalidate queries
      queryClient.invalidateQueries({
        queryKey: ['folderDocuments', options.entityId, options.folderId],
      })
      queryClient.invalidateQueries({
        queryKey: ['categoryDocuments', options.category],
      })
      queryClient.invalidateQueries({
        queryKey: ['entityFolders', options.entityId],
      })

      // Reset state
      setState({
        ...initialState,
        status: 'completed',
      })

      // Call success callback
      options.onSuccess?.(response)

      return response

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Speichern fehlgeschlagen'
      logger.error('[DocumentUpload] Save failed', { error })

      setState(prev => ({
        ...prev,
        status: 'error',
        error: errorMessage,
      }))

      options.onError?.(error instanceof Error ? error : new Error(errorMessage))
      throw error
    }
  }, [state, options, queryClient])

  /**
   * Bricht den aktuellen Upload ab
   */
  const cancel = useCallback(() => {
    if (abortController.current) {
      abortController.current.abort()
    }

    if (state.fileUrl) {
      URL.revokeObjectURL(state.fileUrl)
    }

    setState(initialState)
    logger.info('[DocumentUpload] Upload cancelled')
  }, [state.fileUrl])

  /**
   * Setzt den State zurück
   */
  const reset = useCallback(() => {
    if (state.fileUrl) {
      URL.revokeObjectURL(state.fileUrl)
    }
    setState(initialState)
  }, [state.fileUrl])

  return {
    state,
    startUpload,
    saveDocument,
    cancel,
    reset,

    // Convenience flags
    isProcessing: state.status === 'uploading' || state.status === 'processing' || state.status === 'classifying',
    isReviewReady: state.status === 'review',
    isSaving: state.status === 'saving',
    hasError: state.status === 'error',
  }
}

export type { UseDocumentUploadReturn }
