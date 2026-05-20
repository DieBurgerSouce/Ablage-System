/**
 * Transactions API Service
 *
 * Service für Vorgänge (Document Transactions).
 * Vorgänge verknüpfen Dokumente zu einer Kette:
 * Anfrage → Angebot → Auftrag → Lieferschein → Rechnung → Zahlung
 */

import { apiClient } from '../client';
import type {
  Transaction,
  TransactionListResponse,
  TransactionFilter,
  TransactionStep,
  TransactionStatus,
} from '@/features/ablage/types';

// ==================== Backend Response Types ====================

interface TransactionStepBackend {
  id: string;
  type: string;
  status: string;
  document_id: string | null;
  document_number: string | null;
  completed_at: string | null;
  amount: number | null;
  currency: string;
}

interface TransactionBackend {
  id: string;
  transaction_number: string;
  name: string;
  status: string;
  entity_id: string | null;
  entity_name: string | null;
  folder_id: string | null;
  steps: TransactionStepBackend[];
  total_amount: number | null;
  currency: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  last_activity_at: string;
}

interface TransactionListBackend {
  items: TransactionBackend[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ==================== Transformers ====================

function transformStep(step: TransactionStepBackend): TransactionStep {
  return {
    id: step.id,
    type: step.type as TransactionStep['type'],
    status: step.status as TransactionStep['status'],
    documentId: step.document_id,
    documentNumber: step.document_number,
    completedAt: step.completed_at,
    amount: step.amount,
    currency: step.currency,
  };
}

function transformTransaction(tx: TransactionBackend): Transaction {
  return {
    id: tx.id,
    transactionNumber: tx.transaction_number,
    name: tx.name,
    status: tx.status as TransactionStatus,
    entityId: tx.entity_id || '',
    entityName: tx.entity_name || '',
    folderId: tx.folder_id || '',
    steps: tx.steps.map(transformStep),
    totalAmount: tx.total_amount,
    currency: tx.currency,
    createdAt: tx.created_at,
    updatedAt: tx.updated_at,
    completedAt: tx.completed_at,
    lastActivityAt: tx.last_activity_at,
  };
}

// ==================== API Service ====================

export const transactionsService = {
  /**
   * Listet Transaktionen mit Filterung und Pagination.
   */
  list: async (filter: TransactionFilter): Promise<TransactionListResponse> => {
    const params: Record<string, unknown> = {
      page: filter.page + 1, // Backend erwartet 1-indexed
      per_page: filter.pageSize,
    };

    if (filter.entityId) params.entity_id = filter.entityId;
    if (filter.folderId) params.folder_id = filter.folderId;
    if (filter.status && filter.status.length > 0) {
      params.status_filter = filter.status.join(',');
    }
    if (filter.search) params.search = filter.search;
    if (filter.dateFrom) params.date_from = filter.dateFrom;
    if (filter.dateTo) params.date_to = filter.dateTo;

    const response = await apiClient.get<TransactionListBackend>(
      '/transactions',
      { params }
    );

    return {
      items: response.data.items.map(transformTransaction),
      total: response.data.total,
      page: response.data.page - 1, // Frontend erwartet 0-indexed
      pageSize: response.data.page_size,
      totalPages: response.data.total_pages,
    };
  },

  /**
   * Ruft eine einzelne Transaktion ab.
   */
  get: async (id: string): Promise<Transaction> => {
    const response = await apiClient.get<TransactionBackend>(
      `/transactions/${id}`
    );
    return transformTransaction(response.data);
  },

  /**
   * Erstellt eine neue Transaktion.
   */
  create: async (data: {
    name: string;
    entityId?: string;
    folderId?: string;
    documentIds?: string[];
  }): Promise<Transaction> => {
    const response = await apiClient.post<TransactionBackend>(
      '/transactions',
      {
        name: data.name,
        entity_id: data.entityId,
        folder_id: data.folderId,
        document_ids: data.documentIds || [],
      }
    );
    return transformTransaction(response.data);
  },

  /**
   * Aktualisiert eine Transaktion.
   */
  update: async (
    id: string,
    data: { name?: string; status?: TransactionStatus }
  ): Promise<Transaction> => {
    const response = await apiClient.patch<TransactionBackend>(
      `/transactions/${id}`,
      data
    );
    return transformTransaction(response.data);
  },

  /**
   * Aktualisiert einen Schritt in der Transaktion.
   */
  updateStep: async (
    transactionId: string,
    stepType: string,
    data: {
      status: 'pending' | 'active' | 'completed' | 'skipped';
      documentId?: string;
      amount?: number;
    }
  ): Promise<Transaction> => {
    const response = await apiClient.post<TransactionBackend>(
      `/transactions/${transactionId}/steps/${stepType}`,
      {
        status: data.status,
        document_id: data.documentId,
        amount: data.amount,
      }
    );
    return transformTransaction(response.data);
  },

  /**
   * Löscht eine Transaktion (Soft-Delete).
   */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/transactions/${id}`);
  },
};
