import { apiClient } from '../client';

// ==================== Types ====================

// Dashboard Types
export interface ESGDashboardSummary {
    carbon_footprint: {
        total_co2_kg: number;
        scope_1_kg: number;
        scope_2_kg: number;
        scope_3_kg: number;
        change_percent: number | null;
        period_start: string;
        period_end: string;
    };
    supplier_risk: {
        total_suppliers: number;
        by_risk_level: {
            low: number;
            medium: number;
            high: number;
            critical: number;
        };
        avg_score: number | null;
    };
    certifications: {
        active_count: number;
        expiring_soon_count: number;
        expired_count: number;
    };
    goals: {
        total_count: number;
        on_track_count: number;
        avg_progress: number | null;
    };
    recent_activities: Array<{
        id: string;
        type: string;
        title: string;
        timestamp: string;
        metadata?: Record<string, unknown>;
    }>;
    sdg_mapping: Array<{
        sdg_number: number;
        sdg_name: string;
        goal_count: number;
    }>;
}

// Carbon Footprint Types
export type ESGScope = 'scope_1' | 'scope_2' | 'scope_3';
export type DataQuality = 'high' | 'medium' | 'low' | 'estimated';

export interface EmissionFactor {
    category: string;
    scope: ESGScope;
    factor: number;
    unit: string;
    source: string;
}

export interface CarbonEmission {
    id: string;
    period_start: string;
    period_end: string;
    scope: ESGScope;
    source_category: string;
    source_description: string | null;
    consumption_value: number;
    consumption_unit: string;
    co2_equivalent_kg: number;
    emission_factor: number | null;
    emission_factor_source: string | null;
    data_quality: DataQuality;
    calculation_method: string;
    verified: boolean;
    verified_at: string | null;
    document_id: string | null;
    notes: string | null;
    created_at: string;
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

export interface CarbonEmissionSummary {
    period_start: string;
    period_end: string;
    total_co2_kg: number;
    by_scope: Record<ESGScope, number>;
    by_category: Record<string, number>;
    verified_percentage: number;
    data_quality_breakdown: Record<DataQuality, number>;
}

export interface CarbonTrendEntry {
    month: string;
    total_kg: number;
    scope_1_kg: number;
    scope_2_kg: number;
    scope_3_kg: number;
}

// Supplier Rating Types
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface RatingCriteria {
    category: string;
    criteria: Array<{
        key: string;
        name: string;
        weight: number;
        description: string;
    }>;
}

export interface SupplierRating {
    id: string;
    entity_id: string;
    entity_name: string | null;
    rating_date: string;
    valid_until: string | null;
    overall_score: number;
    environmental_score: number | null;
    social_score: number | null;
    governance_score: number | null;
    environmental_details: Record<string, number>;
    social_details: Record<string, number>;
    governance_details: Record<string, number>;
    risk_level: RiskLevel;
    risk_factors: string[];
    certifications: string[];
    improvement_areas: string[];
    action_plan: string | null;
    assessment_method: string;
    notes: string | null;
    created_at: string;
}

export interface SupplierRatingCreate {
    entity_id: string;
    environmental_details: Record<string, number>;
    social_details: Record<string, number>;
    governance_details: Record<string, number>;
    certifications?: string[];
    improvement_areas?: string[];
    action_plan?: string;
    assessment_method?: string;
    valid_until?: string;
    notes?: string;
}

export interface SupplierRiskSummary {
    total_suppliers: number;
    rated_suppliers: number;
    by_risk_level: Record<RiskLevel, number>;
    avg_overall_score: number | null;
    avg_e_score: number | null;
    avg_s_score: number | null;
    avg_g_score: number | null;
}

// Certification Types
export type CertificationStatus = 'active' | 'expired' | 'pending' | 'revoked';
export type ESGCategory = 'environmental' | 'social' | 'governance';

export interface CertificationType {
    type: string;
    name: string;
    category: ESGCategory;
    description: string;
}

export interface Certification {
    id: string;
    certification_type: string;
    certification_name: string;
    certification_body: string | null;
    certificate_number: string | null;
    category: ESGCategory;
    issue_date: string;
    expiry_date: string | null;
    status: CertificationStatus;
    scope_description: string | null;
    applicable_sites: string[];
    document_id: string | null;
    last_audit_date: string | null;
    next_audit_date: string | null;
    audit_findings: Array<{
        finding: string;
        severity: string;
        resolved: boolean;
    }>;
    reminder_days_before: number;
    notes: string | null;
    created_at: string;
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

export interface CertificationSummary {
    total_count: number;
    active_count: number;
    expiring_soon_count: number;
    expired_count: number;
    pending_count: number;
    by_category: Record<ESGCategory, number>;
    by_type: Record<string, number>;
}

// Report Types
export type ReportStatus = 'draft' | 'in_review' | 'approved' | 'published' | 'archived';
export type ReportType = 'annual' | 'quarterly' | 'csrd' | 'dnk' | 'custom';

export interface ReportTemplate {
    type: ReportType;
    name: string;
    description: string;
    standards: string[];
}

export interface ESGReport {
    id: string;
    title: string;
    report_type: ReportType;
    reporting_standard: string | null;
    period_start: string;
    period_end: string;
    fiscal_year: number | null;
    status: ReportStatus;
    summary: string | null;
    metrics_summary: Record<string, unknown>;
    document_id: string | null;
    pdf_path: string | null;
    created_by_id: string | null;
    approved_by_id: string | null;
    approved_at: string | null;
    published_at: string | null;
    notes: string | null;
    created_at: string;
}

export interface ReportGenerate {
    report_type: ReportType;
    period_start: string;
    period_end: string;
    title?: string;
    reporting_standard?: string;
}

// Goal Types
export interface ESGGoal {
    id: string;
    title: string;
    description: string | null;
    category: ESGCategory;
    metric_name: string;
    metric_unit: string | null;
    baseline_value: number | null;
    baseline_year: number | null;
    target_value: number;
    target_year: number;
    current_value: number | null;
    current_value_date: string | null;
    progress_percentage: number | null;
    on_track: boolean | null;
    sdg_goals: number[];
    is_active: boolean;
    notes: string | null;
    created_at: string;
}

export interface GoalCreate {
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

export interface GoalProgressUpdate {
    current_value: number;
}

// SDG Mapping
export interface SDGMapping {
    sdg_number: number;
    sdg_name: string;
    sdg_description: string;
    goals: Array<{
        id: string;
        title: string;
        progress_percentage: number | null;
    }>;
}

// ==================== ESG Service ====================

export const esgService = {
    // ==================== Dashboard ====================

    getDashboard: async (params?: {
        period_start?: string;
        period_end?: string;
    }) => {
        const response = await apiClient.get<ESGDashboardSummary>('/esg/dashboard', { params });
        return response.data;
    },

    // ==================== Carbon Footprint ====================

    getEmissionFactors: async () => {
        const response = await apiClient.get<{ factors: EmissionFactor[] }>('/esg/carbon-footprint/emission-factors');
        return response.data.factors;
    },

    calculateEmissions: async (params: {
        source_category: string;
        consumption_value: number;
        custom_factor?: number;
    }) => {
        const response = await apiClient.post<{
            co2_equivalent_kg: number;
            emission_factor: number;
            scope: ESGScope;
        }>('/esg/carbon-footprint/calculate', null, { params });
        return response.data;
    },

    recordEmissions: async (data: CarbonEmissionCreate) => {
        const response = await apiClient.post<{
            success: boolean;
            entry_id: string;
            co2_equivalent_kg: number;
        }>('/esg/carbon-footprint', data);
        return response.data;
    },

    getEmissions: async (params?: {
        period_start?: string;
        period_end?: string;
        scope?: ESGScope;
        source_category?: string;
        verified_only?: boolean;
        limit?: number;
        offset?: number;
    }) => {
        const response = await apiClient.get<{
            items: CarbonEmission[];
            total: number;
            limit: number;
            offset: number;
        }>('/esg/carbon-footprint', { params });
        return response.data;
    },

    getEmissionsSummary: async (params: {
        period_start: string;
        period_end: string;
    }) => {
        const response = await apiClient.get<CarbonEmissionSummary>('/esg/carbon-footprint/summary', { params });
        return response.data;
    },

    getCarbonTrend: async (months = 12) => {
        const response = await apiClient.get<CarbonTrendEntry[]>('/esg/carbon-footprint/trend', {
            params: { months },
        });
        return response.data;
    },

    // ==================== Supplier Ratings ====================

    getRatingCriteria: async () => {
        const response = await apiClient.get<{ criteria: RatingCriteria[] }>('/esg/supplier-ratings/criteria');
        return response.data.criteria;
    },

    createSupplierRating: async (data: SupplierRatingCreate) => {
        const response = await apiClient.post<{
            success: boolean;
            rating_id: string;
            overall_score: number;
            risk_level: RiskLevel;
        }>('/esg/supplier-ratings', data);
        return response.data;
    },

    getSupplierRatings: async (params?: {
        entity_id?: string;
        risk_level?: RiskLevel;
        min_score?: number;
        max_score?: number;
        limit?: number;
        offset?: number;
    }) => {
        const response = await apiClient.get<{
            items: SupplierRating[];
            total: number;
            limit: number;
            offset: number;
        }>('/esg/supplier-ratings', { params });
        return response.data;
    },

    getSupplierRiskSummary: async () => {
        const response = await apiClient.get<SupplierRiskSummary>('/esg/supplier-ratings/summary');
        return response.data;
    },

    getLatestSupplierRating: async (entityId: string) => {
        const response = await apiClient.get<SupplierRating>(`/esg/supplier-ratings/${entityId}/latest`);
        return response.data;
    },

    // ==================== Certifications ====================

    getCertificationTypes: async () => {
        const response = await apiClient.get<{ types: CertificationType[] }>('/esg/certifications/types');
        return response.data.types;
    },

    addCertification: async (data: CertificationCreate) => {
        const response = await apiClient.post<{
            success: boolean;
            certification_id: string;
        }>('/esg/certifications', data);
        return response.data;
    },

    getCertifications: async (params?: {
        category?: ESGCategory;
        status?: CertificationStatus;
        include_expired?: boolean;
        limit?: number;
        offset?: number;
    }) => {
        const response = await apiClient.get<{
            items: Certification[];
            total: number;
            limit: number;
            offset: number;
        }>('/esg/certifications', { params });
        return response.data;
    },

    getCertificationSummary: async () => {
        const response = await apiClient.get<CertificationSummary>('/esg/certifications/summary');
        return response.data;
    },

    getExpiringCertifications: async (days = 90) => {
        const response = await apiClient.get<{ items: Certification[] }>('/esg/certifications/expiring', {
            params: { days },
        });
        return response.data.items;
    },

    getUpcomingAudits: async (days = 60) => {
        const response = await apiClient.get<{ items: Certification[] }>('/esg/certifications/upcoming-audits', {
            params: { days },
        });
        return response.data.items;
    },

    getCertificationDetail: async (certificationId: string) => {
        const response = await apiClient.get<Certification>(`/esg/certifications/${certificationId}`);
        return response.data;
    },

    // ==================== Reports ====================

    getReportTemplates: async () => {
        const response = await apiClient.get<{ templates: ReportTemplate[] }>('/esg/reports/templates');
        return response.data.templates;
    },

    generateReport: async (data: ReportGenerate) => {
        const response = await apiClient.post<{
            success: boolean;
            report_id: string;
            title: string;
        }>('/esg/reports/generate', data);
        return response.data;
    },

    getReports: async (params?: {
        report_type?: ReportType;
        status?: ReportStatus;
        limit?: number;
        offset?: number;
    }) => {
        const response = await apiClient.get<{
            items: ESGReport[];
            total: number;
            limit: number;
            offset: number;
        }>('/esg/reports', { params });
        return response.data;
    },

    getReportDetail: async (reportId: string) => {
        const response = await apiClient.get<ESGReport>(`/esg/reports/${reportId}`);
        return response.data;
    },

    // ==================== Goals ====================

    createGoal: async (data: GoalCreate) => {
        const response = await apiClient.post<{
            success: boolean;
            goal_id: string;
        }>('/esg/goals', data);
        return response.data;
    },

    getGoals: async (params?: {
        category?: ESGCategory;
        active_only?: boolean;
    }) => {
        const response = await apiClient.get<{ items: ESGGoal[] }>('/esg/goals', { params });
        return response.data.items;
    },

    updateGoalProgress: async (goalId: string, data: GoalProgressUpdate) => {
        const response = await apiClient.patch<{
            success: boolean;
            progress_percentage: number;
            on_track: boolean;
        }>(`/esg/goals/${goalId}/progress`, data);
        return response.data;
    },

    // ==================== SDG Mapping ====================

    getSDGMapping: async () => {
        const response = await apiClient.get<{ mapping: SDGMapping[] }>('/esg/sdg-mapping');
        return response.data.mapping;
    },
};
