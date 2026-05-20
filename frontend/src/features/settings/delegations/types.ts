/**
 * Delegation Management Types
 *
 * TypeScript types for the delegation system (Vertretungsregelung)
 */

// Enums matching backend
export enum DelegationType {
  FULL = 'full',
  PARTIAL = 'partial',
  APPROVAL = 'approval',
  READ_ONLY = 'read_only',
  EMERGENCY = 'emergency',
}

export enum DelegationStatus {
  PENDING = 'pending',
  ACTIVE = 'active',
  EXPIRED = 'expired',
  REVOKED = 'revoked',
  DECLINED = 'declined',
}

export enum DelegationReason {
  VACATION = 'vacation',
  ILLNESS = 'illness',
  PARENTAL_LEAVE = 'parental_leave',
  BUSINESS_TRIP = 'business_trip',
  PROJECT = 'project',
  TRAINING = 'training',
  OTHER = 'other',
}

// German labels
export const DELEGATION_TYPE_LABELS: Record<DelegationType, string> = {
  [DelegationType.FULL]: 'Vollständige Vertretung',
  [DelegationType.PARTIAL]: 'Teilvertretung',
  [DelegationType.APPROVAL]: 'Nur Genehmigungen',
  [DelegationType.READ_ONLY]: 'Nur Lesezugriff',
  [DelegationType.EMERGENCY]: 'Notfall-Vertretung',
};

export const DELEGATION_TYPE_DESCRIPTIONS: Record<DelegationType, string> = {
  [DelegationType.FULL]: 'Vertreter erhält alle Berechtigungen',
  [DelegationType.PARTIAL]: 'Vertreter erhält ausgewählte Berechtigungen',
  [DelegationType.APPROVAL]: 'Vertreter kann Dokumente genehmigen',
  [DelegationType.READ_ONLY]: 'Vertreter kann nur Dokumente einsehen',
  [DelegationType.EMERGENCY]: 'Sofort aktiv, ohne Bestätigung',
};

export const DELEGATION_STATUS_LABELS: Record<DelegationStatus, string> = {
  [DelegationStatus.PENDING]: 'Ausstehend',
  [DelegationStatus.ACTIVE]: 'Aktiv',
  [DelegationStatus.EXPIRED]: 'Abgelaufen',
  [DelegationStatus.REVOKED]: 'Widerrufen',
  [DelegationStatus.DECLINED]: 'Abgelehnt',
};

export const DELEGATION_REASON_LABELS: Record<DelegationReason, string> = {
  [DelegationReason.VACATION]: 'Urlaub',
  [DelegationReason.ILLNESS]: 'Krankheit',
  [DelegationReason.PARENTAL_LEAVE]: 'Elternzeit',
  [DelegationReason.BUSINESS_TRIP]: 'Dienstreise',
  [DelegationReason.PROJECT]: 'Projektarbeit',
  [DelegationReason.TRAINING]: 'Fortbildung',
  [DelegationReason.OTHER]: 'Sonstiges',
};

// User info for delegation display
export interface DelegationUser {
  id: string;
  email: string;
  display_name?: string;
}

// Main delegation interface
export interface Delegation {
  id: string;
  delegator_id: string;
  delegate_id: string;
  delegator?: DelegationUser;
  delegate?: DelegationUser;
  delegation_type: DelegationType;
  status: DelegationStatus;
  reason: DelegationReason;
  reason_details?: string;
  start_date: string;
  end_date: string;
  permissions?: string[];
  notify_on_action: boolean;
  auto_extend: boolean;
  max_extensions: number;
  extension_count: number;
  created_at: string;
  updated_at: string;
  accepted_at?: string;
  revoked_at?: string;
}

// Create delegation request
export interface DelegationCreateRequest {
  delegate_id: string;
  delegation_type: DelegationType;
  reason: DelegationReason;
  reason_details?: string;
  start_date: string;
  end_date: string;
  permissions?: string[];
  notify_on_action?: boolean;
  auto_extend?: boolean;
  max_extensions?: number;
}

// Update delegation request
export interface DelegationUpdateRequest {
  delegation_type?: DelegationType;
  reason?: DelegationReason;
  reason_details?: string;
  start_date?: string;
  end_date?: string;
  permissions?: string[];
  notify_on_action?: boolean;
  auto_extend?: boolean;
  max_extensions?: number;
}

// API response types
export interface DelegationListResponse {
  delegations: Delegation[];
  total: number;
  page: number;
  page_size: number;
}

export interface DelegationResponse {
  delegation: Delegation;
  nachricht: string;
}

// Delegation template
export interface DelegationTemplate {
  id: string;
  name: string;
  description?: string;
  delegation_type: DelegationType;
  permissions?: string[];
  default_duration_days: number;
  notify_on_action: boolean;
  auto_extend: boolean;
  max_extensions: number;
  is_system: boolean;
  created_at: string;
}

export interface DelegationTemplateListResponse {
  templates: DelegationTemplate[];
  total: number;
}

// Audit log entry
export interface DelegationAuditLog {
  id: string;
  delegation_id: string;
  action: string;
  actor_id: string;
  actor?: DelegationUser;
  details?: Record<string, unknown>;
  created_at: string;
}

export interface DelegationAuditLogResponse {
  logs: DelegationAuditLog[];
  total: number;
}

// Filter options for list queries
export interface DelegationFilters {
  status?: DelegationStatus;
  direction?: 'given' | 'received';
  active_only?: boolean;
}
