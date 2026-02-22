/**
 * Auto-Filing Pipeline Progress Hook.
 *
 * Verfolgt den Fortschritt der automatischen Dokumenten-Zuordnung
 * nach OCR-Verarbeitung. Zeigt Pipeline-Schritte, Konfidenz und
 * Ergebnis in Echtzeit.
 *
 * Pattern: useRealtimeEvent() aus websocket.ts
 */

import { useState, useCallback } from 'react';
import { useRealtimeEvent } from '@/lib/websocket';
import type { RealtimeEvent } from '@/lib/websocket';

export interface PipelineStep {
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  confidence?: number;
  result?: Record<string, unknown>;
}

export interface AutoFilingResult {
  autoProcessed: boolean;
  requiresReview: boolean;
  category?: string;
  entity?: string;
  project?: string;
  reviewReasons?: string[];
  processingTimeMs?: number;
}

export interface AutoFilingProgress {
  /** Ob gerade eine Pipeline laeuft */
  isActive: boolean;
  /** Aktueller Pipeline-Schritt */
  currentStep: string | null;
  /** Alle bisherigen Schritte */
  steps: PipelineStep[];
  /** Ergebnis (wenn fertig) */
  result: AutoFilingResult | null;
  /** Ob Review noetig ist */
  needsReview: boolean;
  /** Ob automatisch abgelegt */
  autoFiled: boolean;
  /** Reset */
  reset: () => void;
}

/**
 * Hook fuer Auto-Filing Pipeline Fortschritt.
 *
 * @param documentId - Document ID zum Tracken (optional, filtert Events)
 *
 * @example
 * const { isActive, currentStep, result, needsReview } = useAutoFilingProgress('doc-123');
 */
export function useAutoFilingProgress(documentId?: string): AutoFilingProgress {
  const [isActive, setIsActive] = useState(false);
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [result, setResult] = useState<AutoFilingResult | null>(null);
  const [needsReview, setNeedsReview] = useState(false);
  const [autoFiled, setAutoFiled] = useState(false);

  const matchesDocument = useCallback(
    (event: RealtimeEvent): boolean => {
      if (!documentId) return true;
      return event.payload?.document_id === documentId;
    },
    [documentId]
  );

  const reset = useCallback(() => {
    setIsActive(false);
    setCurrentStep(null);
    setSteps([]);
    setResult(null);
    setNeedsReview(false);
    setAutoFiled(false);
  }, []);

  // Pipeline gestartet
  useRealtimeEvent('document.pipeline_started', (event) => {
    if (!matchesDocument(event)) return;
    setIsActive(true);
    setCurrentStep('Starte Pipeline...');
    setSteps([]);
    setResult(null);
    setNeedsReview(false);
    setAutoFiled(false);
  });

  // Pipeline-Schritt
  useRealtimeEvent('document.pipeline_step', (event) => {
    if (!matchesDocument(event)) return;
    const stepName = event.payload?.step as string;
    const confidence = event.payload?.confidence as number | undefined;

    setCurrentStep(stepName);
    setSteps((prev) => [
      ...prev.map((s) =>
        s.status === 'running' ? { ...s, status: 'completed' as const } : s
      ),
      {
        name: stepName,
        status: 'running',
        confidence,
      },
    ]);
  });

  // Pipeline abgeschlossen
  useRealtimeEvent('document.pipeline_completed', (event) => {
    if (!matchesDocument(event)) return;
    setIsActive(false);
    setCurrentStep(null);
    setSteps((prev) =>
      prev.map((s) =>
        s.status === 'running' ? { ...s, status: 'completed' as const } : s
      )
    );
  });

  // Automatisch abgelegt
  useRealtimeEvent('document.auto_filed', (event) => {
    if (!matchesDocument(event)) return;
    setAutoFiled(true);
    setIsActive(false);

    const data = event.payload?.data as Record<string, unknown> | undefined;
    setResult({
      autoProcessed: true,
      requiresReview: false,
      category: (data?.category as string) ?? (event.payload?.category as string),
      entity: (data?.entity as string) ?? (event.payload?.entity as string),
      project: (data?.project as string) ?? (event.payload?.project as string),
      processingTimeMs: data?.processing_time_ms as number | undefined,
    });
  });

  // Review noetig
  useRealtimeEvent('document.review_needed', (event) => {
    if (!matchesDocument(event)) return;
    setNeedsReview(true);
    setIsActive(false);

    const data = event.payload?.data as Record<string, unknown> | undefined;
    setResult({
      autoProcessed: false,
      requiresReview: true,
      reviewReasons: (data?.review_reasons as string[]) ?? (event.payload?.review_reasons as string[]),
      category: data?.suggested_category as string | undefined,
      entity: data?.suggested_entity as string | undefined,
    });
  });

  return {
    isActive,
    currentStep,
    steps,
    result,
    needsReview,
    autoFiled,
    reset,
  };
}
