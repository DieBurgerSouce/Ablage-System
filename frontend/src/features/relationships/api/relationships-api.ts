/**
 * Relationships API Service
 *
 * API-Funktionen fuer Cross-Company und Entity-Relationship Ansichten.
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export type EntityType = 'customer' | 'supplier' | 'both' | 'internal';

export interface CompanyStats {
    isPresent: boolean;
    customerNumber?: string | null;
    supplierNumber?: string | null;
    matchcode?: string | null;
    documentCount: number;
    lastActivity?: string | null;
}

export interface CrossCompanyEntity {
    id: string;
    name: string;
    entityType: string;
    isActive: boolean;
    companyPresence: string[];
    companyStats: Record<string, CompanyStats>;
    totalDocuments: number;
    primaryCustomerNumber?: string | null;
    primarySupplierNumber?: string | null;
}

export interface CrossCompanySummary {
    multiCompanyCount: number;
    folieOnlyCount: number;
    messerOnlyCount: number;
    totalEntities: number;
}

export interface CrossCompanyResponse {
    items: CrossCompanyEntity[];
    total: number;
    page: number;
    perPage: number;
    totalPages: number;
    summary: CrossCompanySummary;
}

export interface CrossCompanyParams {
    page?: number;
    perPage?: number;
    search?: string;
    entityType?: EntityType;
    companyFilter?: 'folie' | 'messer';
    multiCompanyOnly?: boolean;
}

// ==================== Timeline Types ====================

export type TimelineEventType = 'document_linked' | 'entity_created' | 'entity_updated';

export interface TimelineEventMetadata {
    documentId?: string;
    filename?: string;
    documentType?: string;
    mimeType?: string;
    entityType?: string;
    [key: string]: string | undefined;
}

export interface TimelineEvent {
    id: string;
    eventType: TimelineEventType;
    title: string;
    description: string;
    timestamp: string | null;
    icon: string;
    metadata: TimelineEventMetadata;
}

export interface EntityTimelineResponse {
    entityId: string;
    entityName: string;
    events: TimelineEvent[];
    total: number;
}

export interface EntityTimelineParams {
    entityId: string;
    limit?: number;
    eventTypes?: TimelineEventType[];
}

// ==================== API Functions ====================

/**
 * Ruft Cross-Company Entity-Uebersicht ab.
 */
export async function fetchCrossCompanyEntities(
    params: CrossCompanyParams = {}
): Promise<CrossCompanyResponse> {
    const queryParams: Record<string, string | number | boolean> = {};

    if (params.page) queryParams.page = params.page;
    if (params.perPage) queryParams.per_page = params.perPage;
    if (params.search) queryParams.search = params.search;
    if (params.entityType) queryParams.entity_type = params.entityType;
    if (params.companyFilter) queryParams.company_filter = params.companyFilter;
    if (params.multiCompanyOnly !== undefined) queryParams.multi_company_only = params.multiCompanyOnly;

    const response = await apiClient.get<CrossCompanyResponse>('/entities/cross-company', {
        params: queryParams,
    });
    return response.data;
}

/**
 * Ruft die Timeline eines Geschaeftspartners ab.
 */
export async function fetchEntityTimeline(
    params: EntityTimelineParams
): Promise<EntityTimelineResponse> {
    const queryParams: Record<string, string | number | string[]> = {};

    if (params.limit) queryParams.limit = params.limit;
    if (params.eventTypes?.length) queryParams.event_types = params.eventTypes;

    const response = await apiClient.get<EntityTimelineResponse>(
        `/entities/${params.entityId}/timeline`,
        { params: queryParams }
    );
    return response.data;
}

// ==================== Dashboard Types ====================

export type DashboardPeriod = '7d' | '30d' | '90d' | '365d';

export interface TopEntity {
    id: string;
    name: string;
    customerNumber?: string | null;
    supplierNumber?: string | null;
    documentCount: number;
    lastActivity: string | null;
}

export interface TrendDataPoint {
    date: string;
    count: number;
}

export interface DashboardSummary {
    totalCustomers: number;
    totalSuppliers: number;
    linkedDocuments: number;
    newEntities: number;
}

export interface DashboardResponse {
    period: string;
    summary: DashboardSummary;
    topCustomers: TopEntity[];
    topSuppliers: TopEntity[];
    documentTrend: TrendDataPoint[];
    typeDistribution: Record<string, number>;
}

// ==================== Dashboard API Functions ====================

/**
 * Ruft Dashboard-Statistiken ab.
 */
export async function fetchDashboardStats(
    period: DashboardPeriod = '30d'
): Promise<DashboardResponse> {
    const response = await apiClient.get<DashboardResponse>(
        '/entities/dashboard/stats',
        { params: { period } }
    );
    return response.data;
}

// ==================== Graph Types ====================

export interface GraphNodePosition {
    x: number;
    y: number;
}

export interface EntityNodeData {
    id: string;
    name: string;
    entityType: string;
    nodeType: 'customer' | 'supplier';
    customerNumber?: string | null;
    supplierNumber?: string | null;
    documentCount: number;
    companyPresence: string[];
}

export interface DocumentNodeData {
    id: string;
    name: string;
    documentType?: string | null;
    icon: string;
    mimeType?: string | null;
}

export interface GraphNode {
    id: string;
    type: 'entityNode' | 'documentNode';
    position: GraphNodePosition;
    data: EntityNodeData | DocumentNodeData;
}

export interface GraphEdge {
    id: string;
    source: string;
    target: string;
    type: string;
    animated: boolean;
    style?: Record<string, string | number>;
}

export interface GraphStatistics {
    totalNodes: number;
    entityNodes: number;
    documentNodes: number;
    customerCount: number;
    supplierCount: number;
    totalEdges: number;
}

export interface GraphResponse {
    nodes: GraphNode[];
    edges: GraphEdge[];
    statistics: GraphStatistics;
}

export interface GraphParams {
    entityType?: EntityType;
    minDocuments?: number;
    includeDocuments?: boolean;
    limit?: number;
}

// ==================== Graph API Functions ====================

/**
 * Ruft Graph-Daten fuer die Entity-Visualisierung ab.
 */
export async function fetchEntityGraphData(
    params: GraphParams = {}
): Promise<GraphResponse> {
    const queryParams: Record<string, string | number | boolean> = {};

    if (params.entityType) queryParams.entity_type = params.entityType;
    if (params.minDocuments !== undefined) queryParams.min_documents = params.minDocuments;
    if (params.includeDocuments !== undefined) queryParams.include_documents = params.includeDocuments;
    if (params.limit) queryParams.limit = params.limit;

    const response = await apiClient.get<GraphResponse>('/entities/graph/data', {
        params: queryParams,
    });
    return response.data;
}

// ==================== Risk Scoring Types ====================

export interface RiskFactors {
    paymentDelayDays: number;
    defaultRate: number;  // As percentage (0-100)
    invoiceVolume: number;
    documentFrequency: number;
    relationshipMonths: number;
    totalInvoices: number;
    paidInvoices: number;
    overdueInvoices: number;
    openInvoices: number;
}

export interface RiskScoreResponse {
    entityId: string;
    entityName: string;
    riskScore: number | null;  // 0-100 (higher = riskier)
    paymentBehaviorScore: number | null;  // 0-100 (higher = better)
    riskFactors: RiskFactors | Record<string, never>;
    calculatedAt: string | null;
}

// ==================== Risk Scoring API Functions ====================

/**
 * Ruft den Risiko-Score eines Geschaeftspartners ab.
 */
export async function fetchEntityRiskScore(entityId: string): Promise<RiskScoreResponse> {
    const response = await apiClient.get<RiskScoreResponse>(`/entities/${entityId}/risk`);
    // Transform snake_case to camelCase
    const data = response.data;
    return {
        entityId: data.entityId,
        entityName: data.entityName,
        riskScore: data.riskScore,
        paymentBehaviorScore: data.paymentBehaviorScore,
        riskFactors: data.riskFactors ? {
            paymentDelayDays: (data.riskFactors as Record<string, number>).payment_delay_days ?? 0,
            defaultRate: (data.riskFactors as Record<string, number>).default_rate ?? 0,
            invoiceVolume: (data.riskFactors as Record<string, number>).invoice_volume ?? 0,
            documentFrequency: (data.riskFactors as Record<string, number>).document_frequency ?? 0,
            relationshipMonths: (data.riskFactors as Record<string, number>).relationship_months ?? 0,
            totalInvoices: (data.riskFactors as Record<string, number>).total_invoices ?? 0,
            paidInvoices: (data.riskFactors as Record<string, number>).paid_invoices ?? 0,
            overdueInvoices: (data.riskFactors as Record<string, number>).overdue_invoices ?? 0,
            openInvoices: (data.riskFactors as Record<string, number>).open_invoices ?? 0,
        } : {},
        calculatedAt: data.calculatedAt,
    };
}

/**
 * Berechnet den Risiko-Score fuer einen Geschaeftspartner neu.
 */
export async function calculateEntityRiskScore(entityId: string): Promise<RiskScoreResponse> {
    const response = await apiClient.post<RiskScoreResponse>(`/entities/${entityId}/risk/calculate`);
    const data = response.data;
    return {
        entityId: data.entityId,
        entityName: data.entityName,
        riskScore: data.riskScore,
        paymentBehaviorScore: data.paymentBehaviorScore,
        riskFactors: data.riskFactors ? {
            paymentDelayDays: (data.riskFactors as Record<string, number>).payment_delay_days ?? 0,
            defaultRate: (data.riskFactors as Record<string, number>).default_rate ?? 0,
            invoiceVolume: (data.riskFactors as Record<string, number>).invoice_volume ?? 0,
            documentFrequency: (data.riskFactors as Record<string, number>).document_frequency ?? 0,
            relationshipMonths: (data.riskFactors as Record<string, number>).relationship_months ?? 0,
            totalInvoices: (data.riskFactors as Record<string, number>).total_invoices ?? 0,
            paidInvoices: (data.riskFactors as Record<string, number>).paid_invoices ?? 0,
            overdueInvoices: (data.riskFactors as Record<string, number>).overdue_invoices ?? 0,
            openInvoices: (data.riskFactors as Record<string, number>).open_invoices ?? 0,
        } : {},
        calculatedAt: data.calculatedAt,
    };
}

// ==================== Query Keys ====================

export const relationshipsQueryKeys = {
    all: ['relationships'] as const,
    crossCompany: (params: CrossCompanyParams) => ['relationships', 'cross-company', params] as const,
    entityTimeline: (entityId: string) => ['relationships', 'timeline', entityId] as const,
    dashboard: (period: DashboardPeriod) => ['relationships', 'dashboard', period] as const,
    graph: (params: GraphParams) => ['relationships', 'graph', params] as const,
    riskScore: (entityId: string) => ['relationships', 'risk', entityId] as const,
};
