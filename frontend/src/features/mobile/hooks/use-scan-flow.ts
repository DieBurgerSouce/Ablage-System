/**
 * useScanFlow Hook
 *
 * Manages the complete scan flow state machine:
 * idle -> scanning -> processing -> result -> assigning
 *
 * Features:
 * - State machine for scan flow phases
 * - OCR status polling via TanStack Query
 * - Entity suggestion loading
 * - Document assignment API
 *
 * Phase 3.2 der Feature-Roadmap (Februar 2026)
 */

import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { logger } from '@/lib/logger';

// ==================== Types ====================

export type ScanFlowPhase = 'idle' | 'scanning' | 'processing' | 'result' | 'assigning';

export interface OCRResultSummary {
  extractedText: string;
  documentType: string | null;
  confidence: number;
  metadata: {
    datum: string | null;
    betrag: string | null;
    absender: string | null;
  };
  matchedEntityId: string | null;
  matchedEntityName: string | null;
}

export interface EntitySuggestion {
  id: string;
  name: string;
  type: 'customer' | 'supplier';
  matchScore: number;
  folderPath: string | null;
}

export interface ScanFlowState {
  phase: ScanFlowPhase;
  documentId: string | null;
  ocrResult: OCRResultSummary | null;
  suggestions: EntitySuggestion[];
}

interface DocumentStatusResponse {
  id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  ocr_confidence: number | null;
  extracted_text: string | null;
  document_type: string | null;
  quick_classification_result: {
    matched_entity_id?: string;
    matched_entity_name?: string;
    direction?: string;
    confidence?: number;
  } | null;
  extracted_metadata: {
    datum?: string;
    betrag?: string;
    absender?: string;
  } | null;
}

interface AssignEntityResponse {
  status: string;
  document_id: string;
  entity_id: string;
}

// ==================== Hook ====================

export function useScanFlow() {
  const [phase, setPhase] = useState<ScanFlowPhase>('idle');
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [ocrResult, setOcrResult] = useState<OCRResultSummary | null>(null);
  const [suggestions, setSuggestions] = useState<EntitySuggestion[]>([]);
  const [pollingEnabled, setPollingEnabled] = useState(false);

  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // ==================== OCR Status Polling ====================

  const { data: documentStatus } = useQuery<DocumentStatusResponse>({
    queryKey: ['document-status', documentId],
    queryFn: async () => {
      if (!documentId) throw new Error('Keine Dokument-ID');
      const response = await apiClient.get<DocumentStatusResponse>(
        `/documents/${documentId}`
      );
      return response.data;
    },
    enabled: phase === 'processing' && documentId !== null && pollingEnabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.status === 'completed' || data?.status === 'failed') {
        return false;
      }
      return 2000;
    },
    refetchIntervalInBackground: false,
  });

  // React to document status changes
  const processDocumentStatus = useCallback(
    (status: DocumentStatusResponse) => {
      if (status.status === 'completed') {
        setPollingEnabled(false);

        const result: OCRResultSummary = {
          extractedText: status.extracted_text || '',
          documentType: status.document_type,
          confidence: status.ocr_confidence ?? 0,
          metadata: {
            datum: status.extracted_metadata?.datum ?? null,
            betrag: status.extracted_metadata?.betrag ?? null,
            absender: status.extracted_metadata?.absender ?? null,
          },
          matchedEntityId: status.quick_classification_result?.matched_entity_id ?? null,
          matchedEntityName: status.quick_classification_result?.matched_entity_name ?? null,
        };

        setOcrResult(result);
        setPhase('result');

        logger.info('[useScanFlow] OCR abgeschlossen', {
          documentId: status.id,
          confidence: result.confidence,
        });
      } else if (status.status === 'failed') {
        setPollingEnabled(false);
        setPhase('result');
        setOcrResult({
          extractedText: '',
          documentType: null,
          confidence: 0,
          metadata: { datum: null, betrag: null, absender: null },
          matchedEntityId: null,
          matchedEntityName: null,
        });

        toast.error('OCR-Verarbeitung fehlgeschlagen', {
          description: 'Das Dokument konnte nicht verarbeitet werden.',
        });
      }
    },
    []
  );

  // Watch for status changes
  if (documentStatus && phase === 'processing') {
    if (documentStatus.status === 'completed' || documentStatus.status === 'failed') {
      processDocumentStatus(documentStatus);
    }
  }

  // ==================== Entity Assignment ====================

  const assignMutation = useMutation({
    mutationFn: async ({ entityId }: { entityId: string }) => {
      if (!documentId) throw new Error('Keine Dokument-ID');
      const response = await apiClient.post<AssignEntityResponse>(
        `/documents/${documentId}/assign-entity`,
        { entity_id: entityId }
      );
      return response.data;
    },
    onSuccess: (_data, { entityId }) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      toast.success('Dokument zugeordnet', {
        description: 'Das Dokument wurde erfolgreich zugeordnet.',
      });
      logger.info('[useScanFlow] Dokument zugeordnet', { documentId, entityId });
    },
    onError: (error) => {
      toast.error('Zuordnung fehlgeschlagen', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
  });

  // ==================== Entity Search ====================

  const loadSuggestions = useCallback(async (searchQuery: string) => {
    try {
      const [customersRes, suppliersRes] = await Promise.all([
        apiClient.get('/entities/customers', {
          params: { search: searchQuery, page_size: '5' },
        }),
        apiClient.get('/entities/suppliers', {
          params: { search: searchQuery, page_size: '5' },
        }),
      ]);

      const customerSuggestions: EntitySuggestion[] = (
        customersRes.data?.items || []
      ).map((c: { id: string; displayName: string; fullName: string }) => ({
        id: c.id,
        name: c.fullName || c.displayName,
        type: 'customer' as const,
        matchScore: 1,
        folderPath: null,
      }));

      const supplierSuggestions: EntitySuggestion[] = (
        suppliersRes.data?.items || []
      ).map((s: { id: string; displayName: string; fullName?: string }) => ({
        id: s.id,
        name: s.fullName || s.displayName,
        type: 'supplier' as const,
        matchScore: 1,
        folderPath: null,
      }));

      setSuggestions([...customerSuggestions, ...supplierSuggestions]);
    } catch (error) {
      logger.error('[useScanFlow] Entity-Suche fehlgeschlagen', { error });
      setSuggestions([]);
    }
  }, []);

  // ==================== Flow Actions ====================

  const startScan = useCallback(() => {
    setPhase('scanning');
    setDocumentId(null);
    setOcrResult(null);
    setSuggestions([]);
  }, []);

  const onUploadComplete = useCallback((newDocumentId: string) => {
    setDocumentId(newDocumentId);
    setPhase('processing');
    setPollingEnabled(true);

    logger.info('[useScanFlow] Upload abgeschlossen, starte Polling', {
      documentId: newDocumentId,
    });
  }, []);

  const startAssigning = useCallback(() => {
    setPhase('assigning');
  }, []);

  const assignToEntity = useCallback(
    async (entityId: string) => {
      await assignMutation.mutateAsync({ entityId });
      if (documentId) {
        navigate({ to: '/documents/$documentId', params: { documentId } });
      }
    },
    [assignMutation, documentId, navigate]
  );

  const scanAnother = useCallback(() => {
    setPhase('idle');
    setDocumentId(null);
    setOcrResult(null);
    setSuggestions([]);
    setPollingEnabled(false);
  }, []);

  const finish = useCallback(() => {
    if (documentId) {
      navigate({ to: '/documents/$documentId', params: { documentId } });
    } else {
      navigate({ to: '/' });
    }
  }, [documentId, navigate]);

  const cancelAssigning = useCallback(() => {
    setPhase('result');
  }, []);

  return {
    // State
    phase,
    documentId,
    ocrResult,
    suggestions,
    isAssigning: assignMutation.isPending,

    // Actions
    startScan,
    onUploadComplete,
    startAssigning,
    assignToEntity,
    scanAnother,
    finish,
    cancelAssigning,
    loadSuggestions,
  };
}

export default useScanFlow;
