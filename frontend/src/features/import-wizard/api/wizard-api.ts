/**
 * Import Wizard API
 *
 * TanStack Query hooks for the import wizard flow
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import type { AxiosError } from 'axios';

// ==================== Types ====================

export interface ImportSource {
  type: 'email' | 'folder' | 'csv';
  label: string;
  description: string;
  icon: string;
}

export interface ImportPreviewResponse {
  itemCount: number;
  totalSize: number;
  warnings: string[];
  sampleItems: Array<{
    filename: string;
    size: number;
    type: string;
    source: string;
  }>;
  estimatedDuration?: string;
}

export interface StartImportRequest {
  configId: string;
  sourceType: 'email' | 'folder';
  dryRun?: boolean;
}

export interface StartImportResponse {
  taskId: string;
  message: string;
  estimatedDuration?: string;
}

// ==================== Error Handling ====================

class WizardApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(message: string, statusCode?: number, originalError?: unknown) {
    super(message);
    this.name = 'WizardApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

function handleApiError(error: unknown, context: string): never {
  if (error instanceof Error && 'response' in error) {
    const axiosError = error as AxiosError<{ detail?: string }>;
    const statusCode = axiosError.response?.status;
    const message = axiosError.response?.data?.detail || axiosError.message;

    throw new WizardApiError(`${context}: ${message}`, statusCode, error);
  }

  throw new WizardApiError(`${context}: Unbekannter Fehler`, undefined, error);
}

// ==================== Hooks ====================

/**
 * Returns available import source types
 */
export function useImportSources() {
  return useQuery<ImportSource[]>({
    queryKey: ['import-wizard', 'sources'],
    queryFn: async () => {
      // Static data - available import sources
      return [
        {
          type: 'email' as const,
          label: 'E-Mail Import',
          description: 'Importiere Dokumente aus E-Mail-Anhängen (IMAP)',
          icon: 'mail',
        },
        {
          type: 'folder' as const,
          label: 'Ordner Import',
          description: 'Überwache lokale oder Netzwerk-Ordner',
          icon: 'folder',
        },
        {
          type: 'csv' as const,
          label: 'CSV/Lexware Import',
          description: 'Importiere Daten aus CSV oder Lexware',
          icon: 'file-spreadsheet',
        },
      ];
    },
    staleTime: Infinity, // Static data never changes
  });
}

/**
 * Preview email import (dry-run)
 */
export function useEmailPreview(configId: string | null) {
  return useQuery<ImportPreviewResponse>({
    queryKey: ['import-wizard', 'email-preview', configId],
    queryFn: async () => {
      if (!configId) {
        throw new Error('Config ID erforderlich');
      }

      try {
        const response = await apiClient.post<ImportPreviewResponse>(
          `/imports/email/configs/${configId}/preview`
        );
        return response.data;
      } catch (error) {
        // Gracefully handle 404 - endpoint may not exist yet
        if (error instanceof Error && 'response' in error) {
          const axiosError = error as AxiosError;
          if (axiosError.response?.status === 404) {
            // Return mock data as fallback
            return {
              itemCount: 0,
              totalSize: 0,
              warnings: ['Vorschau-Funktion noch nicht verfügbar'],
              sampleItems: [],
            };
          }
        }
        handleApiError(error, 'E-Mail Vorschau laden');
      }
    },
    enabled: !!configId,
    retry: false,
  });
}

/**
 * Preview folder import (dry-run)
 */
export function useFolderPreview(configId: string | null) {
  return useQuery<ImportPreviewResponse>({
    queryKey: ['import-wizard', 'folder-preview', configId],
    queryFn: async () => {
      if (!configId) {
        throw new Error('Config ID erforderlich');
      }

      try {
        const response = await apiClient.post<ImportPreviewResponse>(
          `/imports/folder/configs/${configId}/preview`
        );
        return response.data;
      } catch (error) {
        // Gracefully handle 404 - endpoint may not exist yet
        if (error instanceof Error && 'response' in error) {
          const axiosError = error as AxiosError;
          if (axiosError.response?.status === 404) {
            // Return mock data as fallback
            return {
              itemCount: 0,
              totalSize: 0,
              warnings: ['Vorschau-Funktion noch nicht verfügbar'],
              sampleItems: [],
            };
          }
        }
        handleApiError(error, 'Ordner Vorschau laden');
      }
    },
    enabled: !!configId,
    retry: false,
  });
}

/**
 * Start actual import
 */
export function useStartImport() {
  const queryClient = useQueryClient();

  return useMutation<StartImportResponse, Error, StartImportRequest>({
    mutationFn: async (request) => {
      const endpoint =
        request.sourceType === 'email'
          ? `/imports/email/configs/${request.configId}/sync`
          : `/imports/folder/configs/${request.configId}/poll`;

      try {
        const response = await apiClient.post<{
          task_id: string;
          message: string;
        }>(endpoint);

        return {
          taskId: response.data.task_id,
          message: response.data.message,
        };
      } catch (error) {
        handleApiError(error, 'Import starten');
      }
    },
    onSuccess: () => {
      // Invalidate logs after starting import
      void queryClient.invalidateQueries({ queryKey: ['import-logs'] });
    },
  });
}
