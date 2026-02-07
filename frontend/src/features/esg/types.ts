/**
 * ESG (Environmental, Social, Governance) Types
 *
 * TypeScript-Typen fuer das Nachhaltigkeitsberichterstattungs-Modul.
 */

// ==================== Enums ====================

export type ESGScope = 'scope_1' | 'scope_2' | 'scope_3';

export type ESGCategory = 'environmental' | 'social' | 'governance';

export type CertificationStatus = 'active' | 'expired' | 'pending' | 'revoked';

export type ReportStatus = 'draft' | 'in_review' | 'approved' | 'published' | 'archived';

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export type DataQuality = 'high' | 'medium' | 'low' | 'estimated';

export type AssessmentMethod = 'self_assessment' | 'audit' | 'third_party';

// ==================== Dashboard ====================

export interface ESGDashboardSummary {
  carbon_footprint_total: CarbonFootprintSummary;
  supplier_risk_summary: SupplierRiskSummary;
  certification_summary: CertificationSummaryData;
  goal_progress: GoalProgressSummary[];
  period_start?: string;
  period_end?: string;
}

export interface CarbonFootprintSummary {
  total_kg: number;
  scope_1_kg: number;
  scope_2_kg: number;
  scope_3_kg: number;
  change_vs_previous_period?: number;
  top_sources: Array<{
    category: string;
    emissions_kg: number;
    percentage: number;
  }>;
}

export interface SupplierRiskSummary {
  total_rated: number;
  average_score: number;
  by_risk_level: {
    low: number;
    medium: number;
    high: number;
    critical: number;
  };
  requiring_action: number;
}

export interface CertificationSummaryData {
  total_active: number;
  expiring_soon: number;
  by_category: {
    environmental: number;
    social: number;
    governance: number;
  };
  upcoming_audits: number;
}

export interface GoalProgressSummary {
  id: string;
  title: string;
  category: ESGCategory;
  progress_percentage: number;
  on_track: boolean;
  target_year: number;
}

// ==================== Carbon Emissions ====================

export interface CarbonEmission {
  id: string;
  period_start: string;
  period_end: string;
  scope: ESGScope;
  source_category: string;
  source_description?: string;
  consumption_value: number;
  consumption_unit: string;
  co2_equivalent_kg: number;
  emission_factor?: number;
  emission_factor_source?: string;
  data_quality: DataQuality;
  calculation_method?: string;
  document_id?: string;
  verified: boolean;
  verified_at?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface CarbonEmissionCreate {
  period_start: string;
  period_end: string;
  source_category: string;
  consumption_value: number;
  consumption_unit: string;
  source_description?: string;
  custom_factor?: number;
  custom_factor_source?: string;
  document_id?: string;
  data_quality?: DataQuality;
  calculation_method?: string;
  notes?: string;
}

export interface EmissionFactor {
  category: string;
  factor_kg_per_unit: number;
  unit: string;
  source: string;
  scope: ESGScope;
}

export interface EmissionCalculationResult {
  co2_equivalent_kg: number;
  scope: ESGScope;
  emission_factor_used: number;
  emission_factor_source: string;
}

export interface CarbonTrendPoint {
  period: string;
  total_kg: number;
  scope_1_kg: number;
  scope_2_kg: number;
  scope_3_kg: number;
}

// ==================== Supplier Ratings ====================

export interface SupplierRating {
  id: string;
  entity_id: string;
  entity_name?: string;
  rating_date: string;
  valid_until?: string;
  overall_score: number;
  environmental_score?: number;
  social_score?: number;
  governance_score?: number;
  environmental_details?: Record<string, number>;
  social_details?: Record<string, number>;
  governance_details?: Record<string, number>;
  risk_level: RiskLevel;
  risk_factors?: string[];
  certifications?: string[];
  improvement_areas?: string[];
  action_plan?: string;
  assessment_method: AssessmentMethod;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface SupplierRatingCreate {
  entity_id: string;
  environmental_details: Record<string, number>;
  social_details: Record<string, number>;
  governance_details: Record<string, number>;
  certifications?: string[];
  improvement_areas?: string[];
  action_plan?: string;
  assessment_method?: AssessmentMethod;
  valid_until?: string;
  notes?: string;
}

export interface RatingCriterion {
  category: ESGCategory;
  name: string;
  key: string;
  description: string;
  weight: number;
  max_score: number;
}

// ==================== Certifications ====================

export interface Certification {
  id: string;
  certification_type: string;
  certification_name: string;
  certification_body?: string;
  certificate_number?: string;
  category: ESGCategory;
  issue_date: string;
  expiry_date?: string;
  status: CertificationStatus;
  scope_description?: string;
  applicable_sites?: string[];
  document_id?: string;
  last_audit_date?: string;
  next_audit_date?: string;
  reminder_days_before?: number;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface CertificationCreate {
  certification_type: string;
  certification_name: string;
  issue_date: string;
  category: ESGCategory;
  certification_body?: string;
  certificate_number?: string;
  expiry_date?: string;
  scope_description?: string;
  applicable_sites?: string[];
  document_id?: string;
  next_audit_date?: string;
  reminder_days_before?: number;
  notes?: string;
}

export interface CertificationType {
  type: string;
  name: string;
  category: ESGCategory;
  description: string;
}

export interface CertificationSummary {
  total: number;
  by_status: Record<CertificationStatus, number>;
  by_category: Record<ESGCategory, number>;
  expiring_within_90_days: number;
  upcoming_audits_count: number;
}

export interface ExpiringCertification {
  id: string;
  certification_name: string;
  certification_type: string;
  expiry_date: string;
  days_until_expiry: number;
  status: CertificationStatus;
}

export interface UpcomingAudit {
  id: string;
  certification_name: string;
  certification_type: string;
  next_audit_date: string;
  days_until_audit: number;
}

// ==================== Reports ====================

export interface ESGReport {
  id: string;
  title: string;
  report_type: string;
  reporting_standard?: string;
  period_start: string;
  period_end: string;
  fiscal_year?: number;
  status: ReportStatus;
  summary?: string;
  metrics_summary?: Record<string, number>;
  document_id?: string;
  pdf_path?: string;
  created_by_id?: string;
  approved_by_id?: string;
  approved_at?: string;
  published_at?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface ESGReportCreate {
  report_type: string;
  period_start: string;
  period_end: string;
  title?: string;
  reporting_standard?: string;
}

export interface ReportTemplate {
  type: string;
  name: string;
  description: string;
  reporting_standards: string[];
  sections: string[];
}

export interface ReportDetail extends ESGReport {
  content_json?: Record<string, unknown>;
  created_by_name?: string;
  approved_by_name?: string;
}

// ==================== Goals ====================

export interface ESGGoal {
  id: string;
  title: string;
  description?: string;
  category: ESGCategory;
  metric_name: string;
  metric_unit?: string;
  baseline_value?: number;
  baseline_year?: number;
  target_value: number;
  target_year: number;
  current_value?: number;
  current_value_date?: string;
  progress_percentage?: number;
  on_track?: boolean;
  sdg_goals?: number[];
  is_active: boolean;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface ESGGoalCreate {
  title: string;
  description?: string;
  category: ESGCategory;
  metric_name: string;
  metric_unit?: string;
  baseline_value?: number;
  baseline_year?: number;
  target_value: number;
  target_year: number;
  sdg_goals?: number[];
}

export interface ESGGoalProgressUpdate {
  current_value: number;
}

// ==================== SDG Mapping ====================

export interface SDGMapping {
  goal_number: number;
  goal_name: string;
  linked_goals: string[];
  linked_certifications: string[];
  linked_metrics: string[];
}

// ==================== Filter Params ====================

export interface CarbonEmissionFilterParams {
  period_start?: string;
  period_end?: string;
  scope?: ESGScope;
  source_category?: string;
  verified_only?: boolean;
  limit?: number;
  offset?: number;
}

export interface SupplierRatingFilterParams {
  entity_id?: string;
  risk_level?: RiskLevel;
  min_score?: number;
  max_score?: number;
  limit?: number;
  offset?: number;
}

export interface CertificationFilterParams {
  category?: ESGCategory;
  status?: CertificationStatus;
  include_expired?: boolean;
  limit?: number;
  offset?: number;
}

export interface ReportFilterParams {
  report_type?: string;
  status?: ReportStatus;
  limit?: number;
  offset?: number;
}

export interface GoalFilterParams {
  category?: ESGCategory;
  active_only?: boolean;
}

// ==================== API Response Types ====================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface EmissionRecordResponse {
  success: boolean;
  entry_id: string;
  co2_equivalent_kg: number;
}

export interface SupplierRatingResponse {
  success: boolean;
  rating_id: string;
  overall_score: number;
  risk_level: RiskLevel;
}

export interface CertificationAddResponse {
  success: boolean;
  certification_id: string;
}

export interface ReportGenerateResponse {
  success: boolean;
  report_id: string;
  title: string;
}

export interface GoalCreateResponse {
  success: boolean;
  goal_id: string;
}

export interface GoalProgressResponse {
  success: boolean;
  progress_percentage: number;
  on_track: boolean;
}
