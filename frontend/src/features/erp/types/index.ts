/**
 * ERP Integration Types
 *
 * TypeScript-Typen für ERP-Integration:
 * - Verbindungskonfiguration
 * - Sync-Status
 * - Konflikte
 */

export type ERPType = 'odoo' | 'lexware' | 'sap_b1' | 'custom';

export type ERPSyncDirection = 'push' | 'pull' | 'bidirectional';

export type ERPConnectionStatus =
  | 'connected'
  | 'disconnected'
  | 'error'
  | 'authenticating'
  | 'rate_limited';

export type ERPSyncStatus = 'running' | 'success' | 'failed' | 'partial';

export type ERPConflictStatus = 'pending' | 'resolved' | 'ignored';

export type ERPEntityType =
  | 'customer'
  | 'supplier'
  | 'invoice'
  | 'payment'
  | 'product'
  | 'document'
  | 'order';

export interface ERPConnection {
  id: string;
  company_id: string;
  name: string;
  erp_type: ERPType;
  url: string;
  database_name: string | null;
  username: string;

  sync_direction: ERPSyncDirection;
  sync_interval_minutes: number;
  enabled_entities: ERPEntityType[];

  is_active: boolean;
  connection_status: ERPConnectionStatus;
  last_error: string | null;
  last_successful_connection: string | null;

  last_sync_at: string | null;
  last_full_sync_at: string | null;
  next_scheduled_sync: string | null;

  created_at: string;
  updated_at: string;

  /** Effektive Odoo-Firmen-ID (per Verbindung oder globaler Fallback) */
  odoo_company_id: number | null;
}

export interface ERPConnectionCreate {
  name: string;
  erp_type: ERPType;
  url: string;
  database_name?: string;
  username: string;
  api_key: string;

  sync_direction?: ERPSyncDirection;
  sync_interval_minutes?: number;
  enabled_entities?: ERPEntityType[];

  max_requests_per_minute?: number;
  batch_size?: number;

  /** Odoo-interne Firmen-ID (Spargelmesser = 2) */
  odoo_company_id?: number;
}

export interface ERPConnectionUpdate {
  name?: string;
  url?: string;
  database_name?: string;
  username?: string;
  api_key?: string;

  sync_direction?: ERPSyncDirection;
  sync_interval_minutes?: number;
  enabled_entities?: ERPEntityType[];

  max_requests_per_minute?: number;
  batch_size?: number;

  is_active?: boolean;

  /** Odoo-interne Firmen-ID (Spargelmesser = 2) */
  odoo_company_id?: number;
}

/** Status-Zeile des Odoo-Vollarchiv-Spiegels (GET /admin/erp/mirror-status) */
export interface OdooMirrorStatus {
  connection_id: string;
  connection_name: string;
  data_type: string;
  last_sync_cursor: string | null;
  last_sync_at: string | null;
  last_successful_sync_at: string | null;
  total_records_synced: number;
  last_record_count: number | null;
  last_run: Record<string, number> | null;
  consecutive_failures: number;
  is_paused: boolean;
  last_error: string | null;
}

export interface ERPConnectionTestResult {
  success: boolean;
  connected: boolean;
  version: string | null;
  erp_type: ERPType;
  error: string | null;
}

export interface ERPSyncHistory {
  id: string;
  connection_id: string;
  sync_type: 'full' | 'delta' | 'manual';
  entity: ERPEntityType;
  direction: ERPSyncDirection;
  status: ERPSyncStatus;

  records_synced: number;
  records_created: number;
  records_updated: number;
  records_deleted: number;
  records_failed: number;

  conflicts_detected: number;
  conflicts_resolved: number;

  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;

  error_message: string | null;
  triggered_by: string | null;
}

export interface ERPConflict {
  id: string;
  connection_id: string;
  entity: ERPEntityType;
  local_id: string;
  remote_id: string;

  local_data: Record<string, unknown>;
  remote_data: Record<string, unknown>;
  diff: Record<string, unknown> | null;

  local_modified_at: string | null;
  remote_modified_at: string | null;
  detected_at: string;

  status: ERPConflictStatus;
  resolution: 'local_wins' | 'remote_wins' | 'merged' | 'ignored' | null;
  priority: 'low' | 'normal' | 'high' | 'critical';
}

export interface ERPConflictResolve {
  resolution: 'local_wins' | 'remote_wins' | 'merged' | 'ignored';
  resolved_data?: Record<string, unknown>;
  notes?: string;
}

export interface ERPStats {
  total_connections: number;
  active_connections: number;
  pending_conflicts: number;
  syncs_last_24h: number;
}

export interface SyncTriggerResponse {
  message: string;
  task_id: string;
  sync_type: 'full' | 'delta';
}
