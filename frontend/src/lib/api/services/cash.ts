/**
 * Cash/Kassenbuch API Service
 *
 * API-Client für GoBD-konforme Kassenbuchführung.
 *
 * WICHTIG: CashEntry ist APPEND-ONLY!
 */

import { apiClient } from '../client';
import type {
  CashRegister,
  CashRegisterCreate,
  CashRegisterUpdate,
  CashRegisterListResponse,
  CashEntry,
  CashEntryCreate,
  CashEntryCancelRequest,
  CashEntryListResponse,
  DuplicateCheckResult,
  CashCategory,
  CashCategoryCreate,
  CashCount,
  CashCountCreate,
  CashCountListResponse,
  CashBookSummary,
  DailySummary,
  CashEntryType,
} from '@/types/models/cash';

// ==================== Cash Service ====================

export const cashService = {
  // ==================== Registers ====================

  /**
   * Kassen auflisten
   */
  async listRegisters(params?: {
    skip?: number;
    limit?: number;
    include_inactive?: boolean;
  }): Promise<CashRegisterListResponse> {
    const response = await apiClient.get<CashRegisterListResponse>('/cash/registers', { params });
    return response.data;
  },

  /**
   * Kasse abrufen
   */
  async getRegister(registerId: string): Promise<CashRegister> {
    const response = await apiClient.get<CashRegister>(`/cash/registers/${registerId}`);
    return response.data;
  },

  /**
   * Kasse erstellen
   */
  async createRegister(data: CashRegisterCreate): Promise<CashRegister> {
    const response = await apiClient.post<CashRegister>('/cash/registers', data);
    return response.data;
  },

  /**
   * Kasse aktualisieren
   */
  async updateRegister(registerId: string, data: CashRegisterUpdate): Promise<CashRegister> {
    const response = await apiClient.put<CashRegister>(`/cash/registers/${registerId}`, data);
    return response.data;
  },

  // ==================== Entries (APPEND-ONLY!) ====================

  /**
   * Kassenbucheinträge auflisten
   */
  async listEntries(params?: {
    register_id?: string;
    start_date?: string;
    end_date?: string;
    entry_type?: CashEntryType;
    skip?: number;
    limit?: number;
  }): Promise<CashEntryListResponse> {
    const response = await apiClient.get<CashEntryListResponse>('/cash/entries', { params });
    return response.data;
  },

  /**
   * Kassenbucheintrag abrufen
   */
  async getEntry(entryId: string): Promise<CashEntry> {
    const response = await apiClient.get<CashEntry>(`/cash/entries/${entryId}`);
    return response.data;
  },

  /**
   * Kassenbucheintrag erstellen (APPEND-ONLY!)
   *
   * Verwendet Idempotenz-Key um Duplikate bei Netzwerk-Retries zu vermeiden.
   */
  async createEntry(data: CashEntryCreate): Promise<CashEntry> {
    const idempotencyKey = crypto.randomUUID();
    const response = await apiClient.post<CashEntry>('/cash/entries', data, {
      headers: {
        'X-Idempotency-Key': idempotencyKey,
      },
    });
    return response.data;
  },

  /**
   * Prüft auf mögliche Duplikate vor Buchungserstellung.
   * Gibt potentielle Duplikate zurück, damit User entscheiden kann.
   */
  async checkDuplicate(params: {
    register_id: string;
    amount: number;
    entry_date: string;
    description: string;
    receipt_number?: string;
  }): Promise<DuplicateCheckResult> {
    const response = await apiClient.post<DuplicateCheckResult>('/cash/check-duplicate', params);
    return response.data;
  },

  /**
   * Kassenbucheintrag stornieren (via Gegenbuchung)
   */
  async cancelEntry(entryId: string, data: CashEntryCancelRequest): Promise<CashEntry> {
    const response = await apiClient.post<CashEntry>(`/cash/entries/${entryId}/cancel`, data);
    return response.data;
  },

  // ==================== Categories ====================

  /**
   * Kategorien auflisten
   */
  async listCategories(params?: {
    include_inactive?: boolean;
  }): Promise<CashCategory[]> {
    const response = await apiClient.get<CashCategory[]>('/cash/categories', { params });
    return response.data;
  },

  /**
   * Kategorie erstellen
   */
  async createCategory(data: CashCategoryCreate): Promise<CashCategory> {
    const response = await apiClient.post<CashCategory>('/cash/categories', data);
    return response.data;
  },

  // ==================== Cash Count (Kassensturz) ====================

  /**
   * Kassensturz-Protokolle auflisten
   */
  async listCashCounts(params?: {
    register_id?: string;
    start_date?: string;
    end_date?: string;
    skip?: number;
    limit?: number;
  }): Promise<CashCountListResponse> {
    const response = await apiClient.get<CashCountListResponse>('/cash/counts', { params });
    return response.data;
  },

  /**
   * Kassensturz durchführen
   */
  async performCashCount(data: CashCountCreate): Promise<CashCount> {
    const response = await apiClient.post<CashCount>('/cash/counts', data);
    return response.data;
  },

  // ==================== Reports ====================

  /**
   * Kassenbuch-Zusammenfassung abrufen
   */
  async getSummary(params: {
    register_id: string;
    start_date?: string;
    end_date?: string;
  }): Promise<CashBookSummary> {
    const response = await apiClient.get<CashBookSummary>('/cash/summary', { params });
    return response.data;
  },

  /**
   * Tagesabschlüsse abrufen
   */
  async getDailySummaries(params: {
    register_id: string;
    start_date: string;
    end_date: string;
  }): Promise<DailySummary[]> {
    const response = await apiClient.get<DailySummary[]>('/cash/daily', { params });
    return response.data;
  },

  // ==================== Export ====================

  /**
   * Exportiert Kassenbuch als CSV
   */
  async exportCSV(params: {
    register_id: string;
    start_date?: string;
    end_date?: string;
  }): Promise<Blob> {
    const response = await apiClient.get('/cash/export/csv', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },

  /**
   * Exportiert Kassenbuch als PDF
   */
  async exportPDF(params: {
    register_id: string;
    start_date?: string;
    end_date?: string;
  }): Promise<Blob> {
    const response = await apiClient.get('/cash/export/pdf', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },

  /**
   * Exportiert Kassenbuch im DATEV-Format
   */
  async exportDATEV(params: {
    register_id: string;
    start_date?: string;
    end_date?: string;
  }): Promise<Blob> {
    const response = await apiClient.get('/cash/export/datev', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },
};

export default cashService;
