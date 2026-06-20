/**
 * useOfflineApproval Hook
 *
 * React hook for offline approval functionality.
 * Enables:
 * - Quick approvals even when offline
 * - Optimistic UI updates
 * - Queue-based sync when back online
 */

import { useState, useCallback } from 'react';
import { addMutation } from '@/lib/storage/indexed-db';
import { apiClient } from '@/lib/api/client';
import { isOnline } from './offline-api-wrapper';
import { logger } from '@/lib/logger';

// ============================================
// Types
// ============================================

export interface ApprovalAction {
  type: 'approve' | 'reject' | 'defer';
  entityId: string;
  entityType: 'document' | 'invoice' | 'expense' | 'workflow';
  comment?: string;
  metadata?: Record<string, unknown>;
}

export interface ApprovalResult {
  success: boolean;
  queued: boolean;
  error?: string;
}

export interface PendingApproval extends ApprovalAction {
  id: string;
  timestamp: number;
  status: 'pending' | 'synced' | 'failed';
}

export interface UseOfflineApprovalOptions {
  /** Callback after approval (online or queued) */
  onApprovalComplete?: (action: ApprovalAction, result: ApprovalResult) => void;
  /** Enable optimistic updates (default: true) */
  optimisticUpdate?: boolean;
}

export interface UseOfflineApprovalResult {
  /** Submit an approval action */
  submitApproval: (action: ApprovalAction) => Promise<ApprovalResult>;
  /** Bulk approve multiple items */
  bulkApprove: (actions: ApprovalAction[]) => Promise<ApprovalResult[]>;
  /** Quick approve (single click) */
  quickApprove: (entityId: string, entityType: ApprovalAction['entityType']) => Promise<ApprovalResult>;
  /** Quick reject */
  quickReject: (entityId: string, entityType: ApprovalAction['entityType'], comment?: string) => Promise<ApprovalResult>;
  /** Is submission in progress */
  isSubmitting: boolean;
}

// ============================================
// API Endpoint Mapping
// ============================================

function getApprovalEndpoint(action: ApprovalAction): string {
  const baseEndpoints: Record<ApprovalAction['entityType'], string> = {
    document: '/approvals/documents',
    invoice: '/invoices',
    expense: '/expenses',
    workflow: '/workflows',
  };

  const base = baseEndpoints[action.entityType];

  switch (action.type) {
    case 'approve':
      return `${base}/${action.entityId}/approve`;
    case 'reject':
      return `${base}/${action.entityId}/reject`;
    case 'defer':
      return `${base}/${action.entityId}/defer`;
    default:
      return `${base}/${action.entityId}/approve`;
  }
}

// ============================================
// Hook Implementation
// ============================================

export function useOfflineApproval(
  options: UseOfflineApprovalOptions = {}
): UseOfflineApprovalResult {
  const { onApprovalComplete, optimisticUpdate: _optimisticUpdate = true } = options;
  const [isSubmitting, setIsSubmitting] = useState(false);

  /**
   * Submit a single approval action
   */
  const submitApproval = useCallback(
    async (action: ApprovalAction): Promise<ApprovalResult> => {
      setIsSubmitting(true);

      try {
        const endpoint = getApprovalEndpoint(action);
        const payload = {
          comment: action.comment,
          ...action.metadata,
        };

        // If online, make direct API call
        if (isOnline()) {
          try {
            await apiClient.post(endpoint, payload);

            const result: ApprovalResult = {
              success: true,
              queued: false,
            };

            onApprovalComplete?.(action, result);
            return result;
          } catch (error) {
            const errorMessage =
              error instanceof Error ? error.message : 'Unbekannter Fehler';
            logger.error('[OfflineApproval] API-Aufruf fehlgeschlagen', {
              endpoint,
              error: errorMessage,
            });

            return {
              success: false,
              queued: false,
              error: errorMessage,
            };
          }
        }

        // Offline - queue the approval
        await addMutation({
          endpoint,
          method: 'POST',
          payload,
          maxRetries: 5, // Higher retry count for approvals
        });

        logger.info('[OfflineApproval] Genehmigung in Queue gespeichert', {
          entityId: action.entityId,
          type: action.type,
        });

        const result: ApprovalResult = {
          success: true,
          queued: true,
        };

        onApprovalComplete?.(action, result);
        return result;
      } finally {
        setIsSubmitting(false);
      }
    },
    [onApprovalComplete]
  );

  /**
   * Bulk approve multiple items
   */
  const bulkApprove = useCallback(
    async (actions: ApprovalAction[]): Promise<ApprovalResult[]> => {
      setIsSubmitting(true);

      try {
        const results = await Promise.all(
          actions.map((action) => submitApproval(action))
        );
        return results;
      } finally {
        setIsSubmitting(false);
      }
    },
    [submitApproval]
  );

  /**
   * Quick approve shortcut
   */
  const quickApprove = useCallback(
    async (
      entityId: string,
      entityType: ApprovalAction['entityType']
    ): Promise<ApprovalResult> => {
      return submitApproval({
        type: 'approve',
        entityId,
        entityType,
      });
    },
    [submitApproval]
  );

  /**
   * Quick reject shortcut
   */
  const quickReject = useCallback(
    async (
      entityId: string,
      entityType: ApprovalAction['entityType'],
      comment?: string
    ): Promise<ApprovalResult> => {
      return submitApproval({
        type: 'reject',
        entityId,
        entityType,
        comment,
      });
    },
    [submitApproval]
  );

  return {
    submitApproval,
    bulkApprove,
    quickApprove,
    quickReject,
    isSubmitting,
  };
}

export default useOfflineApproval;
