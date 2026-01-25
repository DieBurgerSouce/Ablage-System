/**
 * Dunning Templates Hooks
 * TanStack Query Hooks fuer Mahnbrief-Vorlagen
 */

import { useQuery, useMutation } from '@tanstack/react-query';
import {
  getLetterTemplates,
  getInterestRates,
  getLetterPreview,
  downloadLetterPdf,
  downloadBatchLetters,
} from './api';
import type { LetterPreviewParams, BatchGenerateParams } from './types';

// Query Keys
export const dunningTemplateKeys = {
  all: ['dunning-templates'] as const,
  templates: () => [...dunningTemplateKeys.all, 'templates'] as const,
  interestRates: () => [...dunningTemplateKeys.all, 'interest-rates'] as const,
  preview: (params: LetterPreviewParams) =>
    [...dunningTemplateKeys.all, 'preview', params] as const,
};

// Stale Times
const STALE_TIMES = {
  templates: 30 * 60 * 1000, // 30 Minuten (aendert sich selten)
  interestRates: 60 * 60 * 1000, // 1 Stunde (halbjaehrliche Updates)
};

/**
 * Mahnbrief-Vorlagen abrufen
 */
export function useDunningTemplates() {
  return useQuery({
    queryKey: dunningTemplateKeys.templates(),
    queryFn: getLetterTemplates,
    staleTime: STALE_TIMES.templates,
  });
}

/**
 * Aktuelle Verzugszinssaetze abrufen
 */
export function useInterestRates() {
  return useQuery({
    queryKey: dunningTemplateKeys.interestRates(),
    queryFn: getInterestRates,
    staleTime: STALE_TIMES.interestRates,
  });
}

/**
 * HTML-Vorschau eines Mahnbriefs
 */
export function useLetterPreview(
  params: LetterPreviewParams | null,
  enabled = true
) {
  return useQuery({
    queryKey: params ? dunningTemplateKeys.preview(params) : ['disabled'],
    queryFn: () => (params ? getLetterPreview(params) : Promise.resolve('')),
    enabled: enabled && !!params,
    staleTime: 0, // Immer frisch laden
  });
}

/**
 * Einzelnen Mahnbrief als PDF herunterladen
 */
export function useDownloadLetterPdf() {
  return useMutation({
    mutationFn: downloadLetterPdf,
    onSuccess: (blob, params) => {
      // Trigger Download
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `mahnung_stufe${params.dunningLevel}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    },
  });
}

/**
 * Mehrere Mahnbriefe als ZIP herunterladen
 */
export function useDownloadBatchLetters() {
  return useMutation({
    mutationFn: downloadBatchLetters,
    onSuccess: (blob, params) => {
      // Trigger Download
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const timestamp = new Date().toISOString().slice(0, 10);
      link.download = `mahnbriefe_stufe${params.dunningLevel}_${timestamp}.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    },
  });
}
