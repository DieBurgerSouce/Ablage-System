/**
 * Multi-File Upload Hook fuer Ablage
 *
 * Basiert auf dem Upload Wizard Pattern:
 * - Multiple Dateien gleichzeitig hochladen
 * - Quick Classification fuer jede Datei
 * - Polling fuer OCR-Status
 * - Review-Modal pro Datei oeffenbar
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { logger } from '@/lib/logger';
import type {
  AblageUploadingFile,
  AblageMultiUploadState,
  UseAblageMultiUploadOptions,
  UploadCompleteRequest,
  InvoiceDirection,
} from '../types';
import {
  processDocumentOCR,
  uploadComplete,
  extendTempFileTTL,
} from '../api/ablage-api';

// TTL-Verlaengerung alle 20 Minuten
const TTL_EXTEND_INTERVAL_MS = 20 * 60 * 1000;

// Polling-Interval fuer OCR-Status (nicht gebraucht wenn OCR synchron)
// const OCR_POLL_INTERVAL_MS = 2000;

interface UseAblageMultiUploadReturn {
  // State
  state: AblageMultiUploadState;
  files: AblageUploadingFile[];

  // Actions
  addFiles: (files: File[]) => void;
  removeFile: (id: string) => void;
  openReviewModal: (id: string) => void;
  closeReviewModal: () => void;
  confirmDirection: (id: string, direction: InvoiceDirection) => void;
  confirmRename: (id: string) => Promise<void>;
  saveFile: (id: string, data: Partial<UploadCompleteRequest>) => Promise<void>;
  clearCompleted: () => void;
  cancelAll: () => void;

  // Current Review File
  reviewingFile: AblageUploadingFile | null;

  // Convenience
  isUploading: boolean;
  hasReviewPending: boolean;
  renameLoadingIds: string[];
}

export function useAblageMultiUpload(
  options: UseAblageMultiUploadOptions
): UseAblageMultiUploadReturn {
  const [files, setFiles] = useState<AblageUploadingFile[]>([]);
  const [reviewingFileId, setReviewingFileId] = useState<string | null>(null);
  const [renameLoadingIds, setRenameLoadingIds] = useState<string[]>([]);

  const queryClient = useQueryClient();
  const ttlExtendIntervals = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());
  const abortControllers = useRef<Map<string, AbortController>>(new Map());

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      ttlExtendIntervals.current.forEach((interval) => clearInterval(interval));
      abortControllers.current.forEach((controller) => controller.abort());
    };
  }, []);

  // Start TTL extension for a file in review status
  const startTTLExtension = useCallback((fileId: string, tempFileId: string) => {
    // Clear existing interval if any
    const existingInterval = ttlExtendIntervals.current.get(fileId);
    if (existingInterval) {
      clearInterval(existingInterval);
    }

    // Start new interval
    const interval = setInterval(async () => {
      const success = await extendTempFileTTL(tempFileId);
      if (success) {
        logger.debug('[AblageMultiUpload] TTL extended', { fileId, tempFileId });
      }
    }, TTL_EXTEND_INTERVAL_MS);

    ttlExtendIntervals.current.set(fileId, interval);
  }, []);

  // Stop TTL extension for a file
  const stopTTLExtension = useCallback((fileId: string) => {
    const interval = ttlExtendIntervals.current.get(fileId);
    if (interval) {
      clearInterval(interval);
      ttlExtendIntervals.current.delete(fileId);
    }
  }, []);

  /**
   * Upload a single file and run OCR + Quick Classification
   */
  const uploadSingleFile = useCallback(async (uploadingFile: AblageUploadingFile) => {
    if (!uploadingFile.file) {
      logger.warn('[AblageMultiUpload] uploadSingleFile called without File object');
      return;
    }

    const controller = new AbortController();
    abortControllers.current.set(uploadingFile.id, controller);

    try {
      // Update status to uploading
      setFiles((prev) =>
        prev.map((f) =>
          f.id === uploadingFile.id ? { ...f, status: 'uploading' as const } : f
        )
      );

      // Create preview URL
      const fileUrl = URL.createObjectURL(uploadingFile.file);

      // Call OCR API with progress callback
      const onProgress = (progress: number) => {
        setFiles((prev) =>
          prev.map((f) => {
            if (f.id !== uploadingFile.id) return f;
            // Switch to 'processing' when upload complete
            if (progress >= 100 && f.status === 'uploading') {
              return { ...f, status: 'processing' as const, progress, fileUrl };
            }
            return { ...f, progress, fileUrl };
          })
        );
      };

      const result = await processDocumentOCR(
        uploadingFile.file,
        options.ocrBackend || 'deepseek',
        onProgress
      );

      // Check if cancelled
      if (controller.signal.aborted) {
        logger.info('[AblageMultiUpload] Upload cancelled', { fileId: uploadingFile.id });
        return;
      }

      logger.info('[AblageMultiUpload] OCR completed', {
        fileId: uploadingFile.id,
        success: result.success,
        confidence: result.confidence,
        hasQuickClassification: !!result.quickClassification,
        hasRenameSuggestion: !!result.renameSuggestion,
      });

      // Update file with results
      setFiles((prev) =>
        prev.map((f) =>
          f.id === uploadingFile.id
            ? {
                ...f,
                status: 'review' as const,
                progress: 100,
                fileUrl,
                tempFileId: result.tempFileId,
                ocrResult: {
                  text: result.text,
                  confidence: result.confidence,
                  pageCount: result.pageCount,
                },
                quickClassification: result.quickClassification || undefined,
                renameSuggestion: result.renameSuggestion || undefined,
              }
            : f
        )
      );

      // Start TTL extension
      if (result.tempFileId) {
        startTTLExtension(uploadingFile.id, result.tempFileId);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler';
      logger.error('[AblageMultiUpload] Upload failed', { fileId: uploadingFile.id, error });

      setFiles((prev) =>
        prev.map((f) =>
          f.id === uploadingFile.id
            ? { ...f, status: 'error' as const, error: errorMessage }
            : f
        )
      );

      options.onFileError?.(uploadingFile.id, error instanceof Error ? error : new Error(errorMessage));
    } finally {
      abortControllers.current.delete(uploadingFile.id);
    }
  }, [options, startTTLExtension]);

  /**
   * Add multiple files to the upload queue
   */
  const addFiles = useCallback(
    (newFiles: File[]) => {
      const newUploadingFiles: AblageUploadingFile[] = newFiles.map((file) => ({
        id: crypto.randomUUID(),
        file,
        originalFilename: file.name,
        status: 'pending' as const,
        progress: 0,
      }));

      setFiles((prev) => [...prev, ...newUploadingFiles]);

      // Start uploading each file
      for (const uploadingFile of newUploadingFiles) {
        uploadSingleFile(uploadingFile);
      }
    },
    [uploadSingleFile]
  );

  /**
   * Remove a file from the list
   */
  const removeFile = useCallback(
    (id: string) => {
      const file = files.find((f) => f.id === id);
      if (file) {
        // Stop TTL extension
        stopTTLExtension(id);

        // Abort upload if in progress
        const controller = abortControllers.current.get(id);
        if (controller) {
          controller.abort();
          abortControllers.current.delete(id);
        }

        // Revoke blob URL
        if (file.fileUrl) {
          URL.revokeObjectURL(file.fileUrl);
        }

        // Close review modal if this file was being reviewed
        if (reviewingFileId === id) {
          setReviewingFileId(null);
        }
      }

      setFiles((prev) => prev.filter((f) => f.id !== id));
    },
    [files, reviewingFileId, stopTTLExtension]
  );

  /**
   * Open the review modal for a specific file
   */
  const openReviewModal = useCallback((id: string) => {
    setReviewingFileId(id);
  }, []);

  /**
   * Close the review modal
   */
  const closeReviewModal = useCallback(() => {
    setReviewingFileId(null);
  }, []);

  /**
   * Confirm the invoice direction for a file
   */
  const confirmDirection = useCallback((id: string, direction: InvoiceDirection) => {
    setFiles((prev) =>
      prev.map((f) =>
        f.id === id ? { ...f, confirmedDirection: direction } : f
      )
    );
  }, []);

  /**
   * Confirm the rename suggestion for a file
   */
  const confirmRename = useCallback(async (id: string) => {
    const file = files.find((f) => f.id === id);
    if (!file?.renameSuggestion) return;

    setRenameLoadingIds((prev) => [...prev, id]);

    try {
      // For now, just mark as confirmed (actual rename happens on save)
      setFiles((prev) =>
        prev.map((f) =>
          f.id === id
            ? {
                ...f,
                renameConfirmed: true,
                renamedFilename: file.renameSuggestion?.suggestedFilename,
              }
            : f
        )
      );
    } finally {
      setRenameLoadingIds((prev) => prev.filter((fid) => fid !== id));
    }
  }, [files]);

  /**
   * Save a file (finalize upload)
   */
  const saveFile = useCallback(
    async (id: string, data: Partial<UploadCompleteRequest>) => {
      const file = files.find((f) => f.id === id);
      if (!file?.tempFileId) {
        throw new Error('Keine temporaere Datei vorhanden');
      }

      // Stop TTL extension
      stopTTLExtension(id);

      try {
        // Build complete request
        const request: UploadCompleteRequest = {
          tempFileId: file.tempFileId,
          finalFilename:
            data.finalFilename ||
            file.renamedFilename ||
            file.file?.name ||
            file.originalFilename,
          documentType:
            data.documentType ||
            file.quickClassification?.suggestedDocumentType ||
            'document',
          documentNumber:
            data.documentNumber ||
            file.quickClassification?.extractedData?.documentNumber ||
            undefined,
          documentDate:
            data.documentDate ||
            file.quickClassification?.extractedData?.documentDate ||
            undefined,
          totalAmount:
            data.totalAmount ??
            file.quickClassification?.extractedData?.totalAmount ??
            undefined,
          currency:
            data.currency ||
            file.quickClassification?.extractedData?.currency ||
            'EUR',
          dueDate:
            data.dueDate ||
            file.quickClassification?.extractedData?.dueDate ||
            undefined,
          direction: data.direction || file.confirmedDirection || file.quickClassification?.direction || null,
          ibanFound: data.ibanFound || file.quickClassification?.extractedData?.ibanFound || null,
          vatIdFound: data.vatIdFound || file.quickClassification?.extractedData?.vatIdFound || null,
          businessEntityId:
            data.businessEntityId ||
            file.quickClassification?.matchedEntityId ||
            options.entityId ||
            undefined,
          folderId: data.folderId || options.folderId,
          category: data.category || options.category,
          entityType: data.entityType || options.entityType,
          tags: data.tags || file.quickClassification?.suggestedTags || [],
          ocrText: file.ocrResult?.text || undefined,
          ocrConfidence: file.ocrResult?.confidence || undefined,
        };

        logger.info('[AblageMultiUpload] Saving file', {
          fileId: id,
          tempFileId: request.tempFileId,
          finalFilename: request.finalFilename,
        });

        const response = await uploadComplete(request);

        logger.info('[AblageMultiUpload] File saved', {
          fileId: id,
          documentId: response.documentId,
        });

        // Update file status
        setFiles((prev) =>
          prev.map((f) =>
            f.id === id
              ? {
                  ...f,
                  status: 'completed' as const,
                  documentId: response.documentId,
                }
              : f
          )
        );

        // Cleanup blob URL
        if (file.fileUrl) {
          URL.revokeObjectURL(file.fileUrl);
        }

        // Close review modal
        if (reviewingFileId === id) {
          setReviewingFileId(null);
        }

        // Invalidate queries
        queryClient.invalidateQueries({
          queryKey: ['folderDocuments', options.entityId, options.folderId],
        });
        queryClient.invalidateQueries({
          queryKey: ['categoryDocuments', options.category],
        });
        queryClient.invalidateQueries({
          queryKey: ['entityFolders', options.entityId],
        });

        // Callback
        options.onFileComplete?.(id, response.documentId);

        // Check if all files are complete
        const updatedFiles = files.map((f) =>
          f.id === id ? { ...f, status: 'completed' as const } : f
        );
        const allComplete = updatedFiles.every(
          (f) => f.status === 'completed' || f.status === 'error'
        );
        if (allComplete) {
          options.onAllComplete?.();
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Speichern fehlgeschlagen';
        logger.error('[AblageMultiUpload] Save failed', { fileId: id, error });

        setFiles((prev) =>
          prev.map((f) =>
            f.id === id ? { ...f, status: 'error' as const, error: errorMessage } : f
          )
        );

        throw error;
      }
    },
    [files, options, queryClient, reviewingFileId, stopTTLExtension]
  );

  /**
   * Clear completed files from the list
   */
  const clearCompleted = useCallback(() => {
    setFiles((prev) => {
      const toRemove = prev.filter((f) => f.status === 'completed');
      // Cleanup blob URLs
      toRemove.forEach((f) => {
        if (f.fileUrl) {
          URL.revokeObjectURL(f.fileUrl);
        }
      });
      return prev.filter((f) => f.status !== 'completed');
    });
  }, []);

  /**
   * Cancel all pending uploads
   */
  const cancelAll = useCallback(() => {
    // Abort all in-progress uploads
    abortControllers.current.forEach((controller) => controller.abort());
    abortControllers.current.clear();

    // Stop all TTL extensions
    ttlExtendIntervals.current.forEach((interval) => clearInterval(interval));
    ttlExtendIntervals.current.clear();

    // Cleanup blob URLs
    files.forEach((f) => {
      if (f.fileUrl) {
        URL.revokeObjectURL(f.fileUrl);
      }
    });

    setFiles([]);
    setReviewingFileId(null);
  }, [files]);

  // Compute state
  const state: AblageMultiUploadState = {
    files,
    isUploading: files.some(
      (f) => f.status === 'uploading' || f.status === 'processing'
    ),
    hasErrors: files.some((f) => f.status === 'error'),
    pendingReviewCount: files.filter((f) => f.status === 'review').length,
    completedCount: files.filter((f) => f.status === 'completed').length,
  };

  const reviewingFile = reviewingFileId
    ? files.find((f) => f.id === reviewingFileId) || null
    : null;

  return {
    state,
    files,
    addFiles,
    removeFile,
    openReviewModal,
    closeReviewModal,
    confirmDirection,
    confirmRename,
    saveFile,
    clearCompleted,
    cancelAll,
    reviewingFile,
    isUploading: state.isUploading,
    hasReviewPending: state.pendingReviewCount > 0,
    renameLoadingIds,
  };
}
