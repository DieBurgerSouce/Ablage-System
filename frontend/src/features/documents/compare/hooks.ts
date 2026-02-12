/**
 * Document Comparison Hooks
 *
 * TanStack Query Hooks für Dokumentenvergleiche.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState, type RefObject } from 'react';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';
import type { ComparisonType } from './types';
import {
  compareDocuments,
  getDiffReport,
  findSimilarDocuments,
  findPotentialDuplicates,
} from './api';

// Query Key Factory
export const compareKeys = {
  all: ['compare'] as const,
  comparison: (docId1: string, docId2: string, type?: ComparisonType) =>
    [...compareKeys.all, 'comparison', docId1, docId2, type] as const,
  diffReport: (docId1: string, docId2: string, type?: ComparisonType) =>
    [...compareKeys.all, 'diff-report', docId1, docId2, type] as const,
  similar: (docId: string, threshold?: number) =>
    [...compareKeys.all, 'similar', docId, threshold] as const,
  duplicates: (threshold?: number, daysBack?: number) =>
    [...compareKeys.all, 'duplicates', threshold, daysBack] as const,
};

/**
 * Hook für den Vergleich zweier Dokumente.
 */
export function useCompareDocuments() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: compareDocuments,
    onSuccess: (data) => {
      queryClient.setQueryData(
        compareKeys.comparison(data.documentId1, data.documentId2, data.comparisonType),
        data
      );
    },
  });
}

/**
 * Hook für einen Diff-Report.
 */
export function useDiffReport(
  docId1: string,
  docId2: string,
  comparisonType: ComparisonType = 'hybrid',
  enabled: boolean = true
) {
  return useQuery({
    queryKey: compareKeys.diffReport(docId1, docId2, comparisonType),
    queryFn: () => getDiffReport(docId1, docId2, comparisonType),
    enabled: enabled && !!docId1 && !!docId2,
    staleTime: 5 * 60 * 1000, // 5 Minuten
  });
}

/**
 * Hook für ähnliche Dokumente.
 */
export function useSimilarDocuments(
  docId: string,
  threshold: number = 0.8,
  limit: number = 10,
  includeSameEntity: boolean = true,
  enabled: boolean = true
) {
  return useQuery({
    queryKey: compareKeys.similar(docId, threshold),
    queryFn: () => findSimilarDocuments(docId, threshold, limit, includeSameEntity),
    enabled: enabled && !!docId,
    staleTime: 10 * 60 * 1000, // 10 Minuten
  });
}

/**
 * Hook für potenzielle Duplikate.
 */
export function usePotentialDuplicates(
  threshold: number = 0.95,
  daysBack: number = 30,
  limit: number = 50,
  enabled: boolean = true
) {
  return useQuery({
    queryKey: compareKeys.duplicates(threshold, daysBack),
    queryFn: () => findPotentialDuplicates(threshold, daysBack, limit),
    enabled,
    staleTime: 15 * 60 * 1000, // 15 Minuten
  });
}

// =============================================================================
// PDF Export Hook
// =============================================================================

async function getHtml2Canvas() {
  const module = await import('html2canvas');
  return module.default;
}

async function getJsPdf() {
  const module = await import('jspdf');
  return module.default;
}

interface UseCompareExportReturn {
  exportToPdf: () => Promise<void>;
  isExporting: boolean;
}

/**
 * Hook für PDF-Export des Dokumentenvergleichs.
 * Basiert auf dem useWidgetExport Pattern.
 */
export function useCompareExport(
  containerRef: RefObject<HTMLDivElement | null>,
  filename: string = 'dokumentenvergleich'
): UseCompareExportReturn {
  const [isExporting, setIsExporting] = useState(false);

  const exportToPdf = useCallback(async () => {
    if (!containerRef.current) {
      toast.error('Export-Container nicht gefunden');
      return;
    }

    setIsExporting(true);
    const loadingToast = toast.loading('PDF wird erstellt...');

    try {
      const [html2canvas, jsPDF] = await Promise.all([
        getHtml2Canvas(),
        getJsPdf(),
      ]);

      const canvas = await html2canvas(containerRef.current, {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff',
        windowWidth: containerRef.current.scrollWidth,
        windowHeight: containerRef.current.scrollHeight,
      });

      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF('p', 'mm', 'a4');

      const pdfWidth = pdf.internal.pageSize.getWidth();
      const pdfHeight = pdf.internal.pageSize.getHeight();
      const imgWidth = canvas.width;
      const imgHeight = canvas.height;
      const ratio = pdfWidth / imgWidth;
      const scaledHeight = imgHeight * ratio;

      // Multi-page support für lange Vergleiche
      let heightLeft = scaledHeight;
      let position = 0;
      let page = 0;

      while (heightLeft > 0) {
        if (page > 0) {
          pdf.addPage();
        }

        // Berechne den vertikalen Offset für diese Seite
        const yOffset = -(page * pdfHeight);

        pdf.addImage(imgData, 'PNG', 0, yOffset, pdfWidth, scaledHeight);

        heightLeft -= pdfHeight;
        position += pdfHeight;
        page++;

        // Sicherheitsgrenze (max 50 Seiten)
        if (page > 50) break;
      }

      // Dateiname mit Datum generieren
      const dateStr = new Date().toISOString().split('T')[0];
      const sanitizedFilename = filename
        .replace(/[^a-zA-Z0-9äöüÄÖÜß_-]/g, '_')
        .substring(0, 100);
      const exportFilename = `${sanitizedFilename}_${dateStr}.pdf`;

      pdf.save(exportFilename);

      toast.dismiss(loadingToast);
      toast.success('PDF erfolgreich erstellt', {
        description: exportFilename,
      });
    } catch (error) {
      toast.dismiss(loadingToast);
      const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast.error('PDF-Export fehlgeschlagen', {
        description: errorMessage,
      });
      logger.error('PDF export error:', error);
    } finally {
      setIsExporting(false);
    }
  }, [containerRef, filename]);

  return { exportToPdf, isExporting };
}
