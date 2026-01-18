/**
 * Contract Management Types
 *
 * TypeScript types for B2B contract management.
 */

// =============================================================================
// Enums
// =============================================================================

export enum ContractType {
  SERVICE = 'service',
  SUPPLY = 'supply',
  FRAMEWORK = 'framework',
  MAINTENANCE = 'maintenance',
  LICENSE = 'license',
  LEASE = 'lease',
  CONSULTING = 'consulting',
  COOPERATION = 'cooperation',
  NDA = 'nda',
  PURCHASE = 'purchase',
  OTHER = 'other',
}

export enum ContractStatus {
  DRAFT = 'draft',
  PENDING_SIGNATURE = 'pending_signature',
  ACTIVE = 'active',
  SUSPENDED = 'suspended',
  EXPIRING_SOON = 'expiring_soon',
  EXPIRED = 'expired',
  TERMINATED = 'terminated',
  RENEWED = 'renewed',
}

export enum RenewalOptionStatus {
  AVAILABLE = 'available',
  PENDING = 'pending',
  EXERCISED = 'exercised',
  DECLINED = 'declined',
  EXPIRED = 'expired',
}

export enum MilestoneType {
  CONTRACT_START = 'contract_start',
  CONTRACT_END = 'contract_end',
  RENEWAL_OPTION = 'renewal_option',
  NOTICE_DEADLINE = 'notice_deadline',
  PRICE_ADJUSTMENT = 'price_adjustment',
  SERVICE_LEVEL_REVIEW = 'service_level_review',
  DELIVERABLE_DUE = 'deliverable_due',
  PAYMENT_DUE = 'payment_due',
  AUDIT = 'audit',
  CUSTOM = 'custom',
}

export enum AmendmentStatus {
  DRAFT = 'draft',
  PENDING_APPROVAL = 'pending_approval',
  APPROVED = 'approved',
  REJECTED = 'rejected',
  SUPERSEDED = 'superseded',
}

// =============================================================================
// Display Labels (German)
// =============================================================================

export const CONTRACT_TYPE_LABELS: Record<ContractType, string> = {
  [ContractType.SERVICE]: 'Dienstleistungsvertrag',
  [ContractType.SUPPLY]: 'Liefervertrag',
  [ContractType.FRAMEWORK]: 'Rahmenvertrag',
  [ContractType.MAINTENANCE]: 'Wartungsvertrag',
  [ContractType.LICENSE]: 'Lizenzvertrag',
  [ContractType.LEASE]: 'Mietvertrag',
  [ContractType.CONSULTING]: 'Beratungsvertrag',
  [ContractType.COOPERATION]: 'Kooperationsvertrag',
  [ContractType.NDA]: 'Geheimhaltungsvereinbarung',
  [ContractType.PURCHASE]: 'Kaufvertrag',
  [ContractType.OTHER]: 'Sonstiger Vertrag',
};

export const CONTRACT_STATUS_LABELS: Record<ContractStatus, string> = {
  [ContractStatus.DRAFT]: 'Entwurf',
  [ContractStatus.PENDING_SIGNATURE]: 'Unterschrift ausstehend',
  [ContractStatus.ACTIVE]: 'Aktiv',
  [ContractStatus.SUSPENDED]: 'Ausgesetzt',
  [ContractStatus.EXPIRING_SOON]: 'Laeuft bald ab',
  [ContractStatus.EXPIRED]: 'Abgelaufen',
  [ContractStatus.TERMINATED]: 'Gekuendigt',
  [ContractStatus.RENEWED]: 'Verlaengert',
};

export const RENEWAL_STATUS_LABELS: Record<RenewalOptionStatus, string> = {
  [RenewalOptionStatus.AVAILABLE]: 'Verfuegbar',
  [RenewalOptionStatus.PENDING]: 'Entscheidung ausstehend',
  [RenewalOptionStatus.EXERCISED]: 'Ausgeubt',
  [RenewalOptionStatus.DECLINED]: 'Abgelehnt',
  [RenewalOptionStatus.EXPIRED]: 'Abgelaufen',
};

export const MILESTONE_TYPE_LABELS: Record<MilestoneType, string> = {
  [MilestoneType.CONTRACT_START]: 'Vertragsbeginn',
  [MilestoneType.CONTRACT_END]: 'Vertragsende',
  [MilestoneType.RENEWAL_OPTION]: 'Verlaengerungsoption',
  [MilestoneType.NOTICE_DEADLINE]: 'Kuendigungsfrist',
  [MilestoneType.PRICE_ADJUSTMENT]: 'Preisanpassung',
  [MilestoneType.SERVICE_LEVEL_REVIEW]: 'Service Level Review',
  [MilestoneType.DELIVERABLE_DUE]: 'Liefertermin',
  [MilestoneType.PAYMENT_DUE]: 'Zahlungstermin',
  [MilestoneType.AUDIT]: 'Pruefung',
  [MilestoneType.CUSTOM]: 'Benutzerdefiniert',
};

export const AMENDMENT_STATUS_LABELS: Record<AmendmentStatus, string> = {
  [AmendmentStatus.DRAFT]: 'Entwurf',
  [AmendmentStatus.PENDING_APPROVAL]: 'Genehmigung ausstehend',
  [AmendmentStatus.APPROVED]: 'Genehmigt',
  [AmendmentStatus.REJECTED]: 'Abgelehnt',
  [AmendmentStatus.SUPERSEDED]: 'Ersetzt',
};

// =============================================================================
// Entity Types
// =============================================================================

export interface EntityBrief {
  id: string;
  name: string;
  entity_type?: string;
}

export interface ContractMilestone {
  id: string;
  contract_id: string;
  milestone_type: MilestoneType;
  title: string;
  description?: string;
  scheduled_date: string;
  is_completed: boolean;
  completed_date?: string;
  completion_notes?: string;
  reminder_days_before: number[];
  days_until_due: number;
  is_overdue: boolean;
  created_at: string;
  updated_at: string;
}

export interface ContractRenewalOption {
  id: string;
  contract_id: string;
  option_number: number;
  renewal_duration_months: number;
  price_adjustment_type?: string;
  price_adjustment_value?: number;
  new_monthly_value?: number;
  exercise_deadline: string;
  renewal_start_date: string;
  notice_required_days: number;
  status: RenewalOptionStatus;
  exercised_date?: string;
  exercised_by_id?: string;
  decision_notes?: string;
  days_until_deadline: number;
  is_deadline_critical: boolean;
  created_at: string;
  updated_at: string;
}

export interface ContractAmendment {
  id: string;
  contract_id: string;
  amendment_number: number;
  title: string;
  amendment_date: string;
  effective_date: string;
  changes_summary: string;
  affected_clauses: string[];
  changes_detail: Record<string, unknown>;
  value_change?: number;
  new_total_value?: number;
  document_id?: string;
  status: AmendmentStatus;
  approved_by_id?: string;
  approved_date?: string;
  created_at: string;
  updated_at: string;
}

export interface Contract {
  id: string;
  company_id: string;
  contract_number: string;
  title: string;
  contract_type: ContractType;
  description?: string;
  status: ContractStatus;

  // Parties
  party_a_id?: string;
  party_a_name?: string;
  party_a_signatory?: string;
  party_a?: EntityBrief;
  party_b_id?: string;
  party_b_name?: string;
  party_b_signatory?: string;
  party_b?: EntityBrief;

  // Timeline
  contract_date?: string;
  start_date: string;
  end_date?: string;
  duration_months?: number;
  notice_period_days: number;
  notice_deadline?: string;

  // Renewal
  auto_renewal: boolean;
  renewal_period_months?: number;
  max_renewals?: number;
  current_renewal_count: number;

  // Financial
  total_value?: number;
  monthly_value?: number;
  currency: string;
  payment_terms?: string;

  // Price adjustments
  price_adjustment_clause: boolean;
  price_adjustment_index?: string;
  price_adjustment_date?: string;
  price_adjustment_percent?: number;

  // Legal
  governing_law: string;
  jurisdiction?: string;
  arbitration_clause: boolean;

  // Document
  document_id?: string;

  // Workflow
  signed_date?: string;
  terminated_date?: string;
  termination_reason?: string;

  // Notifications
  reminder_days: number[];
  notification_emails: string[];
  last_reminder_sent?: string;

  // Metadata
  tags: string[];
  metadata: Record<string, unknown>;
  key_contacts: Record<string, unknown>[];
  notes?: string;

  // Computed
  days_until_end?: number;
  days_until_notice_deadline?: number;
  is_expiring_soon: boolean;
  is_notice_deadline_critical: boolean;

  // Audit
  created_at: string;
  updated_at: string;
  created_by_id?: string;
}

export interface ContractDetail extends Contract {
  milestones: ContractMilestone[];
  renewal_options: ContractRenewalOption[];
  amendments: ContractAmendment[];
}

// =============================================================================
// Request/Response Types
// =============================================================================

export interface ContractListResponse {
  items: Contract[];
  total: number;
  offset: number;
  limit: number;
}

export interface DeadlineAlert {
  contract_id: string;
  contract_number: string;
  contract_title: string;
  deadline_type: 'notice' | 'end' | 'renewal';
  deadline_date: string;
  days_remaining: number;
  urgency: 'critical' | 'warning' | 'upcoming';
  party_name?: string;
}

export interface DeadlineListResponse {
  items: DeadlineAlert[];
  total: number;
}

export interface ContractSummary {
  total_contracts: number;
  active_contracts: number;
  expiring_soon: number;
  critical_deadlines: number;
  total_value: number;
  monthly_commitment: number;
}

export interface ContractTimelineEvent {
  event_date: string;
  event_type: string;
  title: string;
  description?: string;
  is_completed: boolean;
  contract_id: string;
}

export interface ContractTimeline {
  contract_id: string;
  contract_number: string;
  events: ContractTimelineEvent[];
}

// =============================================================================
// Form Types
// =============================================================================

export interface ContractCreateRequest {
  contract_number: string;
  title: string;
  contract_type?: ContractType;
  description?: string;

  // Parties
  party_a_id?: string;
  party_a_name?: string;
  party_a_signatory?: string;
  party_b_id?: string;
  party_b_name?: string;
  party_b_signatory?: string;

  // Timeline
  contract_date?: string;
  start_date: string;
  end_date?: string;
  duration_months?: number;

  // Termination and renewal
  notice_period_days?: number;
  auto_renewal?: boolean;
  renewal_period_months?: number;
  max_renewals?: number;

  // Financial
  total_value?: number;
  monthly_value?: number;
  currency?: string;
  payment_terms?: string;

  // Price adjustments
  price_adjustment_clause?: boolean;
  price_adjustment_index?: string;
  price_adjustment_date?: string;
  price_adjustment_percent?: number;

  // Legal
  governing_law?: string;
  jurisdiction?: string;
  arbitration_clause?: boolean;

  // Document
  document_id?: string;

  // Notifications
  reminder_days?: number[];
  notification_emails?: string[];

  // Metadata
  tags?: string[];
  metadata?: Record<string, unknown>;
  key_contacts?: Record<string, unknown>[];
  notes?: string;
}

export interface ContractUpdateRequest extends Partial<ContractCreateRequest> {
  status?: ContractStatus;
  signed_date?: string;
  terminated_date?: string;
  termination_reason?: string;
}

export interface MilestoneCreateRequest {
  milestone_type: MilestoneType;
  title: string;
  description?: string;
  scheduled_date: string;
  reminder_days_before?: number[];
}

export interface MilestoneUpdateRequest extends Partial<MilestoneCreateRequest> {
  is_completed?: boolean;
  completed_date?: string;
  completion_notes?: string;
}

export interface RenewalOptionDecision {
  decision: 'exercise' | 'decline';
  notes?: string;
}

export interface AmendmentCreateRequest {
  title: string;
  amendment_date: string;
  effective_date: string;
  changes_summary: string;
  affected_clauses?: string[];
  changes_detail?: Record<string, unknown>;
  value_change?: number;
  new_total_value?: number;
  document_id?: string;
}

export interface AmendmentUpdateRequest extends Partial<AmendmentCreateRequest> {
  status?: AmendmentStatus;
}

// =============================================================================
// Query Parameters
// =============================================================================

export interface ContractListParams {
  status?: ContractStatus;
  contract_type?: ContractType;
  party_id?: string;
  expiring_within_days?: number;
  search?: string;
  offset?: number;
  limit?: number;
  order_by?: 'contract_number' | 'title' | 'start_date' | 'end_date' | 'notice_deadline' | 'total_value' | 'created_at';
  order_dir?: 'asc' | 'desc';
}
