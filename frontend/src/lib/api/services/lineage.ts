/**
 * Document Lineage API Service
 *
 * API-Service für Datenherkunfts-Tracking.
 * Ermöglicht Abruf der Dokumenten-Timeline und Statistiken.
 */

import { apiClient } from '../client';

// =============================================================================
// Types
// =============================================================================

export type LineageEventType =
  | 'import'
  | 'ocr_start'
  | 'ocr_complete'
  | 'ocr_failed'
  | 'classification'
  | 'extraction'
  | 'entity_link'
  | 'entity_unlink'
  | 'modification'
  | 'metadata_update'
  | 'tag_change'
  | 'approval'
  | 'rejection'
  | 'escalation'
  | 'export'
  | 'archive'
  | 'restore'
  | 'soft_delete'
  | 'hard_delete';

export type ImportSourceType =
  | 'manual_upload'
  | 'email'
  | 'folder'
  | 'api'
  | 'scan'
  | 'integration';

export interface TimelineEntry {
  id: string;
  eventType: LineageEventType;
  eventData: Record<string, unknown>;
  timestamp: string;
  durationMs: number | null;
  confidence: number | null;
  userId: string | null;
  sourceService: string | null;
}

export interface TimelineResponse {
  documentId: string;
  events: TimelineEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface LineageStats {
  documentId: string;
  totalEvents: number;
  totalProcessingDurationMs: number;
  ocr: {
    durationMs: number | null;
    confidence: number | null;
  };
  classification: {
    confidence: number | null;
  };
  entityLinking: {
    confidence: number | null;
  };
  modifications: {
    count: number;
    lastModifiedAt: string | null;
  };
  exports: {
    count: number;
  };
  workflow: {
    approvalCount: number;
    rejectionCount: number;
  };
  importInfo: {
    sourceType: ImportSourceType | null;
    importedAt: string | null;
  };
}

export interface LineageSummary {
  id: string;
  documentId: string;
  importInfo: {
    sourceType: ImportSourceType | null;
    sourceDetails: Record<string, unknown>;
    importedAt: string | null;
    importedById: string | null;
  };
  ocr: {
    backend: string | null;
    durationMs: number | null;
    confidence: number | null;
    completedAt: string | null;
  };
  classification: {
    confidence: number | null;
    classifiedAt: string | null;
  };
  entityLinking: {
    currentEntityId: string | null;
    confidence: number | null;
    linkedAt: string | null;
    linkCount: number;
  };
  modifications: {
    count: number;
    lastModifiedAt: string | null;
    lastModifiedById: string | null;
  };
  statistics: {
    totalProcessingDurationMs: number;
    totalEventCount: number;
    approvalCount: number;
    rejectionCount: number;
    exportCount: number;
  };
  lastExportedAt: string | null;
  companyId: string;
  createdAt: string;
  updatedAt: string;
}

export interface EventTypeLabels {
  [key: string]: string;
}

// =============================================================================
// Transform Functions (Backend snake_case -> Frontend camelCase)
// =============================================================================

interface TimelineEntryBackend {
  id: string;
  event_type: string;
  event_data: Record<string, unknown>;
  timestamp: string;
  duration_ms: number | null;
  confidence: number | null;
  user_id: string | null;
  source_service: string | null;
}

interface TimelineResponseBackend {
  document_id: string;
  events: TimelineEntryBackend[];
  total: number;
  limit: number;
  offset: number;
}

interface LineageStatsBackend {
  document_id: string;
  total_events: number;
  total_processing_duration_ms: number;
  ocr: {
    duration_ms: number | null;
    confidence: number | null;
  };
  classification: {
    confidence: number | null;
  };
  entity_linking: {
    confidence: number | null;
  };
  modifications: {
    count: number;
    last_modified_at: string | null;
  };
  exports: {
    count: number;
  };
  workflow: {
    approval_count: number;
    rejection_count: number;
  };
  import_info: {
    source_type: string | null;
    imported_at: string | null;
  };
}

interface LineageSummaryBackend {
  id: string;
  document_id: string;
  import_info: {
    source_type: string | null;
    source_details: Record<string, unknown>;
    imported_at: string | null;
    imported_by_id: string | null;
  };
  ocr: {
    backend: string | null;
    duration_ms: number | null;
    confidence: number | null;
    completed_at: string | null;
  };
  classification: {
    confidence: number | null;
    classified_at: string | null;
  };
  entity_linking: {
    current_entity_id: string | null;
    confidence: number | null;
    linked_at: string | null;
    link_count: number;
  };
  modifications: {
    count: number;
    last_modified_at: string | null;
    last_modified_by_id: string | null;
  };
  statistics: {
    total_processing_duration_ms: number;
    total_event_count: number;
    approval_count: number;
    rejection_count: number;
    export_count: number;
  };
  last_exported_at: string | null;
  company_id: string;
  created_at: string;
  updated_at: string;
}

function transformTimelineEntry(entry: TimelineEntryBackend): TimelineEntry {
  return {
    id: entry.id,
    eventType: entry.event_type as LineageEventType,
    eventData: entry.event_data,
    timestamp: entry.timestamp,
    durationMs: entry.duration_ms,
    confidence: entry.confidence,
    userId: entry.user_id,
    sourceService: entry.source_service,
  };
}

function transformTimelineResponse(response: TimelineResponseBackend): TimelineResponse {
  return {
    documentId: response.document_id,
    events: response.events.map(transformTimelineEntry),
    total: response.total,
    limit: response.limit,
    offset: response.offset,
  };
}

function transformStats(stats: LineageStatsBackend): LineageStats {
  return {
    documentId: stats.document_id,
    totalEvents: stats.total_events,
    totalProcessingDurationMs: stats.total_processing_duration_ms,
    ocr: {
      durationMs: stats.ocr.duration_ms,
      confidence: stats.ocr.confidence,
    },
    classification: {
      confidence: stats.classification.confidence,
    },
    entityLinking: {
      confidence: stats.entity_linking.confidence,
    },
    modifications: {
      count: stats.modifications.count,
      lastModifiedAt: stats.modifications.last_modified_at,
    },
    exports: {
      count: stats.exports.count,
    },
    workflow: {
      approvalCount: stats.workflow.approval_count,
      rejectionCount: stats.workflow.rejection_count,
    },
    importInfo: {
      sourceType: stats.import_info.source_type as ImportSourceType | null,
      importedAt: stats.import_info.imported_at,
    },
  };
}

function transformSummary(summary: LineageSummaryBackend): LineageSummary {
  return {
    id: summary.id,
    documentId: summary.document_id,
    importInfo: {
      sourceType: summary.import_info.source_type as ImportSourceType | null,
      sourceDetails: summary.import_info.source_details,
      importedAt: summary.import_info.imported_at,
      importedById: summary.import_info.imported_by_id,
    },
    ocr: {
      backend: summary.ocr.backend,
      durationMs: summary.ocr.duration_ms,
      confidence: summary.ocr.confidence,
      completedAt: summary.ocr.completed_at,
    },
    classification: {
      confidence: summary.classification.confidence,
      classifiedAt: summary.classification.classified_at,
    },
    entityLinking: {
      currentEntityId: summary.entity_linking.current_entity_id,
      confidence: summary.entity_linking.confidence,
      linkedAt: summary.entity_linking.linked_at,
      linkCount: summary.entity_linking.link_count,
    },
    modifications: {
      count: summary.modifications.count,
      lastModifiedAt: summary.modifications.last_modified_at,
      lastModifiedById: summary.modifications.last_modified_by_id,
    },
    statistics: {
      totalProcessingDurationMs: summary.statistics.total_processing_duration_ms,
      totalEventCount: summary.statistics.total_event_count,
      approvalCount: summary.statistics.approval_count,
      rejectionCount: summary.statistics.rejection_count,
      exportCount: summary.statistics.export_count,
    },
    lastExportedAt: summary.last_exported_at,
    companyId: summary.company_id,
    createdAt: summary.created_at,
    updatedAt: summary.updated_at,
  };
}

// =============================================================================
// API Service
// =============================================================================

export interface GetTimelineParams {
  limit?: number;
  offset?: number;
  eventTypes?: LineageEventType[];
}

export const lineageService = {
  /**
   * Ruft die vollständige Lineage-Timeline eines Dokuments ab.
   */
  getTimeline: async (
    documentId: string,
    params?: GetTimelineParams
  ): Promise<TimelineResponse> => {
    const queryParams: Record<string, string | number> = {};

    if (params?.limit) queryParams.limit = params.limit;
    if (params?.offset) queryParams.offset = params.offset;
    if (params?.eventTypes && params.eventTypes.length > 0) {
      queryParams.event_types = params.eventTypes.join(',');
    }

    const response = await apiClient.get<TimelineResponseBackend>(
      `/documents/${documentId}/lineage`,
      { params: queryParams }
    );

    return transformTimelineResponse(response.data);
  },

  /**
   * Ruft aggregierte Statistiken zur Dokumenten-Lineage ab.
   */
  getStats: async (documentId: string): Promise<LineageStats> => {
    const response = await apiClient.get<LineageStatsBackend>(
      `/documents/${documentId}/lineage/stats`
    );

    return transformStats(response.data);
  },

  /**
   * Ruft die vollständige Lineage-Zusammenfassung ab.
   */
  getSummary: async (documentId: string): Promise<LineageSummary> => {
    const response = await apiClient.get<LineageSummaryBackend>(
      `/documents/${documentId}/lineage/summary`
    );

    return transformSummary(response.data);
  },

  /**
   * Gibt alle verfügbaren Event-Typen mit deutschen Labels zurück.
   */
  getEventTypes: async (): Promise<EventTypeLabels> => {
    const response = await apiClient.get<EventTypeLabels>(
      '/documents/lineage/event-types'
    );

    return response.data;
  },

  /**
   * Gibt alle verfügbaren Import-Quelltypen mit deutschen Labels zurück.
   */
  getImportSourceTypes: async (): Promise<Record<string, string>> => {
    const response = await apiClient.get<Record<string, string>>(
      '/documents/lineage/import-source-types'
    );

    return response.data;
  },

  /**
   * Exportiert die Lineage-Daten eines Dokuments.
   */
  exportLineage: async (
    documentId: string,
    format: 'json' | 'pdf' = 'json'
  ): Promise<Blob> => {
    const response = await apiClient.get(
      `/documents/${documentId}/lineage/export`,
      {
        params: { format },
        responseType: 'blob',
      }
    );

    return response.data;
  },
};
