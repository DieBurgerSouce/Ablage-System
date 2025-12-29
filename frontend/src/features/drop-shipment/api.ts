/**
 * Streckengeschäft API Client
 *
 * Handles all API calls for drop shipment / triangular transaction
 * classification, confirmation, and DATEV export.
 *
 * Backend Router: /api/v1/streckengeschaeft
 */

import { apiClient } from '@/lib/api/client';
import type {
  DropShipmentClassification,
  DropShipmentListFilter,
  DropShipmentListResponse,
  ClassifyDocumentRequest,
  ClassifyDocumentResponse,
  ConfirmClassificationRequest,
  OverrideClassificationRequest,
  LinkProofDocumentRequest,
  ZmPendingResponse,
  DatevExportRequest,
  DatevExportResponse,
  DropShipmentDashboardStats,
  BulkActionRequest,
  BulkActionResponse,
  ProofDocument,
} from './types';

// API path matches backend router: /api/v1/streckengeschaeft
const BASE_URL = '/api/v1/streckengeschaeft';

/**
 * Transform axios response to data
 */
function extractData<T>(response: { data: T }): T {
  return response.data;
}

/**
 * Streckengeschäft API
 */
export const dropShipmentApi = {
  /**
   * Liste aller Streckengeschäft-Klassifikationen mit Filtern
   * Backend: GET /classifications
   */
  async list(filter?: DropShipmentListFilter): Promise<DropShipmentListResponse> {
    const params = new URLSearchParams();

    if (filter?.classificationType?.length) {
      params.set('transaction_type', filter.classificationType[0]);
    }
    if (filter?.confidenceMin !== undefined) {
      params.set('confidence_level',
        filter.confidenceMin >= 0.9 ? 'high' :
        filter.confidenceMin >= 0.7 ? 'medium' : 'low'
      );
    }
    if (filter?.isConfirmed !== undefined) {
      params.set('is_validated', filter.isConfirmed.toString());
    }
    if (filter?.zmRelevant !== undefined) {
      params.set('zm_relevant', filter.zmRelevant.toString());
    }
    if (filter?.dateFrom) {
      params.set('date_from', filter.dateFrom);
    }
    if (filter?.dateTo) {
      params.set('date_to', filter.dateTo);
    }
    if (filter?.page !== undefined) {
      params.set('page', filter.page.toString());
    }
    if (filter?.pageSize !== undefined) {
      params.set('page_size', filter.pageSize.toString());
    }
    if (filter?.sortBy) {
      params.set('sort_by', filter.sortBy);
    }
    if (filter?.sortOrder) {
      params.set('sort_order', filter.sortOrder);
    }

    const queryString = params.toString();
    const url = queryString ? `${BASE_URL}/classifications?${queryString}` : `${BASE_URL}/classifications`;

    const response = await apiClient.get<DropShipmentListResponse>(url);
    return extractData(response);
  },

  /**
   * Einzelne Klassifikation mit allen Details abrufen
   * Backend: GET /classifications/{classification_id}
   */
  async getById(id: string): Promise<DropShipmentClassification> {
    const response = await apiClient.get<DropShipmentClassification>(
      `${BASE_URL}/classifications/${id}?include_audit_log=true`
    );
    return extractData(response);
  },

  /**
   * Klassifikation für ein Dokument auslösen
   * Backend: POST /classify
   */
  async classifyDocument(request: ClassifyDocumentRequest): Promise<ClassifyDocumentResponse> {
    const response = await apiClient.post<ClassifyDocumentResponse>(
      `${BASE_URL}/classify`,
      {
        document_id: request.documentId,
        force_reclassify: request.forceReclassify ?? false,
        skip_validation: false,
      }
    );
    return extractData(response);
  },

  /**
   * Klassifikation manuell bestätigen/validieren
   * Backend: PATCH /classifications/{classification_id}/validate
   */
  async confirm(request: ConfirmClassificationRequest): Promise<DropShipmentClassification> {
    const response = await apiClient.patch<{ classification: DropShipmentClassification }>(
      `${BASE_URL}/classifications/${request.classificationId}/validate`,
      {
        classification_id: request.classificationId,
        validated_transaction_type: request.confirmedType ?? 'drop_shipment',
        validated_company_role: 'intermediate',
        validated_vat_category: 'K',
        reason: request.notes,
      }
    );
    return extractData(response).classification;
  },

  /**
   * Klassifikation manuell überschreiben/korrigieren
   * Backend: PATCH /classifications/{classification_id}/validate
   */
  async override(request: OverrideClassificationRequest): Promise<DropShipmentClassification> {
    const response = await apiClient.patch<{ classification: DropShipmentClassification }>(
      `${BASE_URL}/classifications/${request.classificationId}/validate`,
      {
        classification_id: request.classificationId,
        validated_transaction_type: request.newClassificationType,
        validated_company_role: request.movingDeliveryAssignedTo ?? 'intermediate',
        validated_vat_category: request.taxTreatment === 'tax_free_ic' ? 'K' : 'S',
        reason: request.reason,
      }
    );
    return extractData(response).classification;
  },

  /**
   * Belegnachweis-Dokumente für eine Klassifikation abrufen
   * Backend: GET /classifications/{classification_id}/proofs
   */
  async getProofDocuments(classificationId: string): Promise<{
    classification_id: string;
    proof_documents: ProofDocument[];
    completeness: { required: number; complete: number; percentage: number };
  }> {
    const response = await apiClient.get<{
      classification_id: string;
      proof_documents: ProofDocument[];
      completeness: { required: number; complete: number; percentage: number };
    }>(`${BASE_URL}/classifications/${classificationId}/proofs`);
    return extractData(response);
  },

  /**
   * Belegnachweis mit Klassifikation verknüpfen (Frontend-only, kein Backend-Endpoint)
   */
  async linkProofDocument(request: LinkProofDocumentRequest): Promise<ProofDocument> {
    // Note: Backend doesn't have explicit link endpoint - handled via classification update
    const response = await apiClient.post<ProofDocument>(
      `${BASE_URL}/classifications/${request.classificationId}/proofs`,
      {
        proof_type: request.proofType,
        document_id: request.documentId,
      }
    );
    return extractData(response);
  },

  /**
   * Belegnachweis entfernen
   */
  async unlinkProofDocument(classificationId: string, proofDocumentId: string): Promise<void> {
    await apiClient.delete(`${BASE_URL}/classifications/${classificationId}/proofs/${proofDocumentId}`);
  },

  /**
   * ZM-Summary für aktuelle Periode abrufen
   * Backend: GET /zm/summary
   */
  async getZmPending(): Promise<ZmPendingResponse> {
    // Get current period (YYYY-MM)
    const now = new Date();
    const period = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

    const response = await apiClient.get<ZmPendingResponse>(
      `${BASE_URL}/zm/summary?period=${period}`
    );
    return extractData(response);
  },

  /**
   * ZM-Summary für spezifische Periode abrufen
   * Backend: GET /zm/summary
   */
  async getZmSummary(period: string): Promise<ZmPendingResponse> {
    const response = await apiClient.get<ZmPendingResponse>(
      `${BASE_URL}/zm/summary?period=${period}`
    );
    return extractData(response);
  },

  /**
   * Als ZM-gemeldet markieren (via validate endpoint)
   */
  async markZmReported(classificationId: string, reportDate: string): Promise<DropShipmentClassification> {
    const response = await apiClient.patch<{ classification: DropShipmentClassification }>(
      `${BASE_URL}/classifications/${classificationId}/validate`,
      {
        classification_id: classificationId,
        validated_transaction_type: 'drop_shipment',
        validated_company_role: 'intermediate',
        validated_vat_category: 'K',
        reason: `ZM gemeldet am ${reportDate}`,
      }
    );
    return extractData(response).classification;
  },

  /**
   * VAT-ID validieren via VIES
   * Backend: POST /vat-id/validate
   */
  async validateVatId(vatId: string, requesterVatId?: string): Promise<{
    vat_id: string;
    is_valid: boolean;
    company_name?: string;
    address?: string;
    validated_at: string;
  }> {
    const response = await apiClient.post<{
      vat_id: string;
      is_valid: boolean;
      company_name?: string;
      address?: string;
      validated_at: string;
    }>(`${BASE_URL}/vat-id/validate`, {
      vat_id: vatId,
      requester_vat_id: requesterVatId,
    });
    return extractData(response);
  },

  /**
   * DATEV-Export ausführen
   * Backend: POST /datev/export
   */
  async exportDatev(request: DatevExportRequest): Promise<DatevExportResponse> {
    const response = await apiClient.post<{
      success: boolean;
      export_id: string;
      filename: string;
      download_url: string;
      record_count: number;
      zm_record_count?: number;
      warnings?: string[];
    }>(`${BASE_URL}/datev/export`, {
      classification_ids: request.classificationIds,
      kontenrahmen: `SKR${request.kontenrahmen}`,
      include_zm_data: request.includeZmData,
      export_format: request.exportFormat,
    });

    const data = extractData(response);
    return {
      exportId: data.export_id,
      fileName: data.filename,
      downloadUrl: data.download_url,
      recordCount: data.record_count,
      warnings: data.warnings,
    };
  },

  /**
   * Dashboard-Statistiken
   * Backend: GET /statistics
   */
  async getDashboardStats(): Promise<DropShipmentDashboardStats> {
    const response = await apiClient.get<DropShipmentDashboardStats>(
      `${BASE_URL}/statistics`
    );
    return extractData(response);
  },

  /**
   * Bulk-Klassifikation für mehrere Dokumente
   * Backend: POST /classify/bulk
   */
  async bulkClassify(request: {
    documentIds: string[];
    forceReclassify?: boolean;
    skipLowConfidence?: boolean;
  }): Promise<BulkActionResponse> {
    const response = await apiClient.post<{
      successful: string[];
      failed: Array<{ id: string; error: string }>;
      summary: { total: number; classified: number; failed: number; manual_required: number };
    }>(`${BASE_URL}/classify/bulk`, {
      document_ids: request.documentIds,
      force_reclassify: request.forceReclassify ?? false,
      skip_low_confidence: request.skipLowConfidence ?? false,
    });

    const data = extractData(response);
    return {
      successful: data.successful,
      failed: data.failed,
    };
  },

  /**
   * Bulk-Aktionen (Bestätigen, Export, ZM markieren)
   */
  async bulkAction(request: BulkActionRequest): Promise<BulkActionResponse> {
    if (request.action === 'confirm') {
      // Validate all classifications in sequence
      const successful: string[] = [];
      const failed: Array<{ id: string; error: string }> = [];

      for (const id of request.classificationIds) {
        try {
          await this.confirm({ classificationId: id });
          successful.push(id);
        } catch (error) {
          failed.push({ id, error: String(error) });
        }
      }

      return { successful, failed };
    } else if (request.action === 'export_datev') {
      // Use DATEV export endpoint
      await this.exportDatev({
        classificationIds: request.classificationIds,
        exportFormat: 'extf',
        kontenrahmen: '03',
        includeZmData: true,
      });
      return { successful: request.classificationIds, failed: [] };
    } else {
      // mark_zm_reported
      const successful: string[] = [];
      const failed: Array<{ id: string; error: string }> = [];
      const today = new Date().toISOString().split('T')[0];

      for (const id of request.classificationIds) {
        try {
          await this.markZmReported(id, today);
          successful.push(id);
        } catch (error) {
          failed.push({ id, error: String(error) });
        }
      }

      return { successful, failed };
    }
  },

  /**
   * Klassifikation löschen (nur unbestätigte)
   */
  async delete(classificationId: string): Promise<void> {
    await apiClient.delete(`${BASE_URL}/classifications/${classificationId}`);
  },

  /**
   * Verknüpfte Dokumente für Dokumentenfluss-Validierung abrufen
   */
  async getRelatedDocuments(classificationId: string): Promise<{
    purchaseOrders: Array<{ id: string; number: string; date: string }>;
    deliveryNotes: Array<{ id: string; number: string; date: string }>;
    cmrDocuments: Array<{ id: string; number: string; date: string }>;
    invoices: Array<{ id: string; number: string; date: string }>;
  }> {
    // Use proof documents endpoint as source
    const proofsResponse = await this.getProofDocuments(classificationId);

    // Transform proof documents to related documents format
    return {
      purchaseOrders: [],
      deliveryNotes: proofsResponse.proof_documents
        .filter(p => p.proofType === 'lieferschein')
        .map(p => ({ id: p.id, number: p.documentName ?? '', date: p.createdAt })),
      cmrDocuments: proofsResponse.proof_documents
        .filter(p => p.proofType === 'cmr')
        .map(p => ({ id: p.id, number: p.documentName ?? '', date: p.createdAt })),
      invoices: [],
    };
  },

  /**
   * Automatische Dokumentenfluss-Validierung
   */
  async validateDocumentFlow(classificationId: string): Promise<{
    isValid: boolean;
    issues: Array<{
      severity: 'error' | 'warning';
      message: string;
      documentType?: string;
    }>;
  }> {
    // Use proof documents completeness check
    const proofsResponse = await this.getProofDocuments(classificationId);

    const issues: Array<{ severity: 'error' | 'warning'; message: string; documentType?: string }> = [];

    if (proofsResponse.completeness.percentage < 100) {
      const missing = proofsResponse.proof_documents.filter(p => !p.isComplete);
      for (const doc of missing) {
        issues.push({
          severity: 'error',
          message: `Fehlender Belegnachweis: ${doc.proofType}`,
          documentType: doc.proofType,
        });
      }
    }

    return {
      isValid: issues.length === 0,
      issues,
    };
  },
};

export default dropShipmentApi;
