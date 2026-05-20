/**
 * Budget API Service
 *
 * Kommuniziert mit den /api/v1/budgets Endpoints
 * für Budget-Verwaltung mit Kostenstellen
 *
 * Features:
 * - Kostenstellen-Verwaltung (hierarchisch)
 * - Budget-CRUD mit Perioden (Monat/Quartal/Jahr)
 * - Budget-Positionen und Zuweisungen
 * - Abweichungsberichte (Soll/Ist)
 * - Alert-System bei Überschreitung
 *
 * Phase 2.1 der Feature-Roadmap (Januar 2026)
 */

import { AxiosError } from 'axios';
import { apiClient } from '../client';

// ==================== Error Classes ====================

export class BudgetApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(message: string, statusCode?: number, originalError?: unknown) {
    super(message);
    this.name = 'BudgetApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Enums ====================

export type BudgetPeriodType = 'monthly' | 'quarterly' | 'yearly' | 'custom';
export type BudgetStatus = 'draft' | 'active' | 'closed' | 'archived';
export type BudgetLineStatus = 'under_budget' | 'on_track' | 'warning' | 'critical' | 'exceeded';
export type AllocationSource = 'manual' | 'ocr_auto' | 'import' | 'rule_based';
export type AlertSeverity = 'info' | 'warning' | 'critical' | 'exceeded';

// ==================== Frontend Types ====================

export interface Kostenstelle {
  id: string;
  code: string;
  name: string;
  description?: string;
  parentId?: string;
  level: number;
  path?: string;
  isActive: boolean;
  companyId: string;
  responsibleUserId?: string;
  defaultBudgetCategoryId?: string;
  createdAt: string;
  updatedAt: string;
}

export interface KostenstelleTreeNode extends Kostenstelle {
  children: KostenstelleTreeNode[];
}

export interface Budget {
  id: string;
  name: string;
  description?: string;
  companyId: string;
  periodType: BudgetPeriodType;
  year: number;
  quarter?: number;
  month?: number;
  startDate: string;
  endDate: string;
  status: BudgetStatus;
  totalPlanned: number;
  totalActual: number;
  warningThreshold: number;
  criticalThreshold: number;
  currency: string;
  isTemplate: boolean;
  templateSourceId?: string;
  approvedAt?: string;
  approvedById?: string;
  closedAt?: string;
  notes?: string;
  createdAt: string;
  updatedAt: string;
  utilizationPercent: number;
  lines?: BudgetLine[];
}

export interface BudgetLine {
  id: string;
  budgetId: string;
  kostenstelleId?: string;
  parentLineId?: string;
  category: string;
  subcategory?: string;
  plannedAmount: number;
  actualAmount: number;
  status: BudgetLineStatus;
  notes?: string;
  autoAssignRules: AutoAssignRule[];
  sortOrder: number;
  createdAt: string;
  updatedAt: string;
  remainingAmount: number;
  utilizationPercent: number;
  kostenstelle?: Kostenstelle;
}

export interface AutoAssignRule {
  field: string;
  operator: string;
  value: string;
  category?: string;
}

export interface BudgetAllocation {
  id: string;
  budgetLineId: string;
  documentId?: string;
  amount: number;
  source: AllocationSource;
  description?: string;
  ocrConfidence?: number;
  ocrExtractedCategory?: string;
  allocatedAt: string;
  allocatedById?: string;
  reversedAt?: string;
  reversedById?: string;
  reverseReason?: string;
  metadata?: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface BudgetAlert {
  id: string;
  budgetId: string;
  budgetLineId?: string;
  severity: AlertSeverity;
  message: string;
  thresholdPercent: number;
  actualPercent: number;
  isAcknowledged: boolean;
  acknowledgedAt?: string;
  acknowledgedById?: string;
  notificationSentAt?: string;
  createdAt: string;
}

export interface BudgetSummary {
  budgetId: string;
  budgetName: string;
  periodLabel: string;
  status: BudgetStatus;
  totalPlanned: number;
  totalActual: number;
  totalRemaining: number;
  utilizationPercent: number;
  lineCount: number;
  kostenstelleCount: number;
  unacknowledgedAlerts: number;
  byCategory: CategorySummary[];
  byKostenstelle: KostenstelleSummary[];
  recentAllocations: RecentAllocation[];
}

export interface CategorySummary {
  category: string;
  planned: number;
  actual: number;
  utilization: number;
  status: BudgetLineStatus;
}

export interface KostenstelleSummary {
  kostenstelleId: string;
  kostenstelleName: string;
  kostenstelleCode: string;
  planned: number;
  actual: number;
  utilization: number;
}

export interface RecentAllocation {
  id: string;
  amount: number;
  category: string;
  source: AllocationSource;
  allocatedAt: string;
  documentName?: string;
}

export interface BudgetVarianceReport {
  budgetId: string;
  periodStart: string;
  periodEnd: string;
  lines: VarianceLine[];
  totalVariance: number;
  totalVariancePercent: number;
  byCategory: Record<string, CategoryVariance>;
  byKostenstelle: Record<string, KostenstelleVariance>;
  recommendations: string[];
  generatedAt: string;
}

export interface VarianceLine {
  lineId: string;
  category: string;
  subcategory?: string;
  kostenstelleCode?: string;
  planned: number;
  actual: number;
  variance: number;
  variancePercent: number;
  status: BudgetLineStatus;
}

export interface CategoryVariance {
  planned: number;
  actual: number;
  variance: number;
  variancePercent: number;
}

export interface KostenstelleVariance {
  name: string;
  code: string;
  planned: number;
  actual: number;
  variance: number;
  variancePercent: number;
}

// ==================== Request Types ====================

export interface KostenstelleCreateRequest {
  code: string;
  name: string;
  description?: string;
  parentId?: string;
  responsibleUserId?: string;
  defaultBudgetCategoryId?: string;
}

export interface BudgetCreateRequest {
  name: string;
  description?: string;
  periodType: BudgetPeriodType;
  year: number;
  quarter?: number;
  month?: number;
  startDate?: string;
  endDate?: string;
  warningThreshold?: number;
  criticalThreshold?: number;
  currency?: string;
  isTemplate?: boolean;
  templateSourceId?: string;
  notes?: string;
}

export interface BudgetLineCreateRequest {
  kostenstelleId?: string;
  parentLineId?: string;
  category: string;
  subcategory?: string;
  plannedAmount: number;
  notes?: string;
  autoAssignRules?: AutoAssignRule[];
  sortOrder?: number;
}

export interface AllocationCreateRequest {
  budgetLineId: string;
  documentId?: string;
  amount: number;
  source?: AllocationSource;
  description?: string;
  ocrConfidence?: number;
  ocrExtractedCategory?: string;
  metadata?: Record<string, unknown>;
}

export interface BudgetFilter {
  companyId?: string;
  year?: number;
  periodType?: BudgetPeriodType;
  status?: BudgetStatus;
  isTemplate?: boolean;
  search?: string;
}

// ==================== Backend Types ====================

interface KostenstelleBackend {
  id: string;
  code: string;
  name: string;
  description: string | null;
  parent_id: string | null;
  level: number;
  path: string | null;
  is_active: boolean;
  company_id: string;
  responsible_user_id: string | null;
  default_budget_category_id: string | null;
  created_at: string;
  updated_at: string;
}

interface KostenstelleTreeNodeBackend extends KostenstelleBackend {
  children: KostenstelleTreeNodeBackend[];
}

interface BudgetBackend {
  id: string;
  name: string;
  description: string | null;
  company_id: string;
  period_type: BudgetPeriodType;
  year: number;
  quarter: number | null;
  month: number | null;
  start_date: string;
  end_date: string;
  status: BudgetStatus;
  total_planned: number;
  total_actual: number;
  warning_threshold: number;
  critical_threshold: number;
  currency: string;
  is_template: boolean;
  template_source_id: string | null;
  approved_at: string | null;
  approved_by_id: string | null;
  closed_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  utilization_percent: number;
  lines?: BudgetLineBackend[];
}

interface BudgetLineBackend {
  id: string;
  budget_id: string;
  kostenstelle_id: string | null;
  parent_line_id: string | null;
  category: string;
  subcategory: string | null;
  planned_amount: number;
  actual_amount: number;
  status: BudgetLineStatus;
  notes: string | null;
  auto_assign_rules: AutoAssignRule[];
  sort_order: number;
  created_at: string;
  updated_at: string;
  remaining_amount: number;
  utilization_percent: number;
  kostenstelle?: KostenstelleBackend;
}

interface BudgetAllocationBackend {
  id: string;
  budget_line_id: string;
  document_id: string | null;
  amount: number;
  source: AllocationSource;
  description: string | null;
  ocr_confidence: number | null;
  ocr_extracted_category: string | null;
  allocated_at: string;
  allocated_by_id: string | null;
  reversed_at: string | null;
  reversed_by_id: string | null;
  reverse_reason: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

interface BudgetAlertBackend {
  id: string;
  budget_id: string;
  budget_line_id: string | null;
  severity: AlertSeverity;
  message: string;
  threshold_percent: number;
  actual_percent: number;
  is_acknowledged: boolean;
  acknowledged_at: string | null;
  acknowledged_by_id: string | null;
  notification_sent_at: string | null;
  created_at: string;
}

interface BudgetSummaryBackend {
  budget_id: string;
  budget_name: string;
  period_label: string;
  status: BudgetStatus;
  total_planned: number;
  total_actual: number;
  total_remaining: number;
  utilization_percent: number;
  line_count: number;
  kostenstelle_count: number;
  unacknowledged_alerts: number;
  by_category: {
    category: string;
    planned: number;
    actual: number;
    utilization: number;
    status: BudgetLineStatus;
  }[];
  by_kostenstelle: {
    kostenstelle_id: string;
    kostenstelle_name: string;
    kostenstelle_code: string;
    planned: number;
    actual: number;
    utilization: number;
  }[];
  recent_allocations: {
    id: string;
    amount: number;
    category: string;
    source: AllocationSource;
    allocated_at: string;
    document_name: string | null;
  }[];
}

interface BudgetVarianceReportBackend {
  budget_id: string;
  period_start: string;
  period_end: string;
  lines: {
    line_id: string;
    category: string;
    subcategory: string | null;
    kostenstelle_code: string | null;
    planned: number;
    actual: number;
    variance: number;
    variance_percent: number;
    status: BudgetLineStatus;
  }[];
  total_variance: number;
  total_variance_percent: number;
  by_category: Record<string, { planned: number; actual: number; variance: number; variance_percent: number }>;
  by_kostenstelle: Record<string, { name: string; code: string; planned: number; actual: number; variance: number; variance_percent: number }>;
  recommendations: string[];
  generated_at: string;
}

interface BudgetListBackend {
  items: BudgetBackend[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface AllocationListBackend {
  items: BudgetAllocationBackend[];
  total: number;
  page: number;
  page_size: number;
}

// ==================== Transformers ====================

function transformKostenstelle(k: KostenstelleBackend): Kostenstelle {
  return {
    id: k.id,
    code: k.code,
    name: k.name,
    description: k.description ?? undefined,
    parentId: k.parent_id ?? undefined,
    level: k.level,
    path: k.path ?? undefined,
    isActive: k.is_active,
    companyId: k.company_id,
    responsibleUserId: k.responsible_user_id ?? undefined,
    defaultBudgetCategoryId: k.default_budget_category_id ?? undefined,
    createdAt: k.created_at,
    updatedAt: k.updated_at,
  };
}

function transformKostenstelleTree(k: KostenstelleTreeNodeBackend): KostenstelleTreeNode {
  return {
    ...transformKostenstelle(k),
    children: k.children.map(transformKostenstelleTree),
  };
}

function transformBudgetLine(line: BudgetLineBackend): BudgetLine {
  return {
    id: line.id,
    budgetId: line.budget_id,
    kostenstelleId: line.kostenstelle_id ?? undefined,
    parentLineId: line.parent_line_id ?? undefined,
    category: line.category,
    subcategory: line.subcategory ?? undefined,
    plannedAmount: line.planned_amount,
    actualAmount: line.actual_amount,
    status: line.status,
    notes: line.notes ?? undefined,
    autoAssignRules: line.auto_assign_rules ?? [],
    sortOrder: line.sort_order,
    createdAt: line.created_at,
    updatedAt: line.updated_at,
    remainingAmount: line.remaining_amount,
    utilizationPercent: line.utilization_percent,
    kostenstelle: line.kostenstelle ? transformKostenstelle(line.kostenstelle) : undefined,
  };
}

function transformBudget(b: BudgetBackend): Budget {
  return {
    id: b.id,
    name: b.name,
    description: b.description ?? undefined,
    companyId: b.company_id,
    periodType: b.period_type,
    year: b.year,
    quarter: b.quarter ?? undefined,
    month: b.month ?? undefined,
    startDate: b.start_date,
    endDate: b.end_date,
    status: b.status,
    totalPlanned: b.total_planned,
    totalActual: b.total_actual,
    warningThreshold: b.warning_threshold,
    criticalThreshold: b.critical_threshold,
    currency: b.currency,
    isTemplate: b.is_template,
    templateSourceId: b.template_source_id ?? undefined,
    approvedAt: b.approved_at ?? undefined,
    approvedById: b.approved_by_id ?? undefined,
    closedAt: b.closed_at ?? undefined,
    notes: b.notes ?? undefined,
    createdAt: b.created_at,
    updatedAt: b.updated_at,
    utilizationPercent: b.utilization_percent,
    lines: b.lines?.map(transformBudgetLine),
  };
}

function transformAllocation(a: BudgetAllocationBackend): BudgetAllocation {
  return {
    id: a.id,
    budgetLineId: a.budget_line_id,
    documentId: a.document_id ?? undefined,
    amount: a.amount,
    source: a.source,
    description: a.description ?? undefined,
    ocrConfidence: a.ocr_confidence ?? undefined,
    ocrExtractedCategory: a.ocr_extracted_category ?? undefined,
    allocatedAt: a.allocated_at,
    allocatedById: a.allocated_by_id ?? undefined,
    reversedAt: a.reversed_at ?? undefined,
    reversedById: a.reversed_by_id ?? undefined,
    reverseReason: a.reverse_reason ?? undefined,
    metadata: a.metadata ?? undefined,
    createdAt: a.created_at,
    updatedAt: a.updated_at,
  };
}

function transformAlert(a: BudgetAlertBackend): BudgetAlert {
  return {
    id: a.id,
    budgetId: a.budget_id,
    budgetLineId: a.budget_line_id ?? undefined,
    severity: a.severity,
    message: a.message,
    thresholdPercent: a.threshold_percent,
    actualPercent: a.actual_percent,
    isAcknowledged: a.is_acknowledged,
    acknowledgedAt: a.acknowledged_at ?? undefined,
    acknowledgedById: a.acknowledged_by_id ?? undefined,
    notificationSentAt: a.notification_sent_at ?? undefined,
    createdAt: a.created_at,
  };
}

function transformBudgetSummary(s: BudgetSummaryBackend): BudgetSummary {
  return {
    budgetId: s.budget_id,
    budgetName: s.budget_name,
    periodLabel: s.period_label,
    status: s.status,
    totalPlanned: s.total_planned,
    totalActual: s.total_actual,
    totalRemaining: s.total_remaining,
    utilizationPercent: s.utilization_percent,
    lineCount: s.line_count,
    kostenstelleCount: s.kostenstelle_count,
    unacknowledgedAlerts: s.unacknowledged_alerts,
    byCategory: s.by_category.map((c) => ({
      category: c.category,
      planned: c.planned,
      actual: c.actual,
      utilization: c.utilization,
      status: c.status,
    })),
    byKostenstelle: s.by_kostenstelle.map((k) => ({
      kostenstelleId: k.kostenstelle_id,
      kostenstelleName: k.kostenstelle_name,
      kostenstelleCode: k.kostenstelle_code,
      planned: k.planned,
      actual: k.actual,
      utilization: k.utilization,
    })),
    recentAllocations: s.recent_allocations.map((a) => ({
      id: a.id,
      amount: a.amount,
      category: a.category,
      source: a.source,
      allocatedAt: a.allocated_at,
      documentName: a.document_name ?? undefined,
    })),
  };
}

function transformVarianceReport(r: BudgetVarianceReportBackend): BudgetVarianceReport {
  return {
    budgetId: r.budget_id,
    periodStart: r.period_start,
    periodEnd: r.period_end,
    lines: r.lines.map((l) => ({
      lineId: l.line_id,
      category: l.category,
      subcategory: l.subcategory ?? undefined,
      kostenstelleCode: l.kostenstelle_code ?? undefined,
      planned: l.planned,
      actual: l.actual,
      variance: l.variance,
      variancePercent: l.variance_percent,
      status: l.status,
    })),
    totalVariance: r.total_variance,
    totalVariancePercent: r.total_variance_percent,
    byCategory: Object.fromEntries(
      Object.entries(r.by_category).map(([key, val]) => [
        key,
        {
          planned: val.planned,
          actual: val.actual,
          variance: val.variance,
          variancePercent: val.variance_percent,
        },
      ])
    ),
    byKostenstelle: Object.fromEntries(
      Object.entries(r.by_kostenstelle).map(([key, val]) => [
        key,
        {
          name: val.name,
          code: val.code,
          planned: val.planned,
          actual: val.actual,
          variance: val.variance,
          variancePercent: val.variance_percent,
        },
      ])
    ),
    recommendations: r.recommendations,
    generatedAt: r.generated_at,
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new BudgetApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 400) {
      throw new BudgetApiError(`${context}: ${message}`, 400, error);
    }

    throw new BudgetApiError(`${context}: ${message}`, statusCode, error);
  }

  throw new BudgetApiError(`${context}: Unbekannter Fehler`, undefined, error);
}

// ==================== Budget Service ====================

export const budgetService = {
  // ==================== Kostenstellen ====================

  /**
   * Erstellt eine neue Kostenstelle
   */
  createKostenstelle: async (request: KostenstelleCreateRequest): Promise<Kostenstelle> => {
    try {
      const response = await apiClient.post<KostenstelleBackend>('/budgets/kostenstellen', {
        code: request.code,
        name: request.name,
        description: request.description,
        parent_id: request.parentId,
        responsible_user_id: request.responsibleUserId,
        default_budget_category_id: request.defaultBudgetCategoryId,
      });
      return transformKostenstelle(response.data);
    } catch (error) {
      handleApiError(error, 'Kostenstelle erstellen');
    }
  },

  /**
   * Listet Kostenstellen auf
   */
  listKostenstellen: async (params?: {
    parentId?: string;
    activeOnly?: boolean;
  }): Promise<Kostenstelle[]> => {
    try {
      const queryParams = new URLSearchParams();
      if (params?.parentId) queryParams.append('parent_id', params.parentId);
      if (params?.activeOnly !== undefined) queryParams.append('active_only', String(params.activeOnly));

      const url = `/budgets/kostenstellen${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
      const response = await apiClient.get<KostenstelleBackend[]>(url);
      return response.data.map(transformKostenstelle);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Kostenstellen laden');
    }
  },

  /**
   * Holt den Kostenstellen-Baum
   */
  getKostenstelleTree: async (): Promise<KostenstelleTreeNode[]> => {
    try {
      const response = await apiClient.get<KostenstelleTreeNodeBackend[]>('/budgets/kostenstellen/tree');
      return response.data.map(transformKostenstelleTree);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Kostenstellen-Baum laden');
    }
  },

  // ==================== Budgets ====================

  /**
   * Erstellt ein neues Budget
   */
  createBudget: async (request: BudgetCreateRequest): Promise<Budget> => {
    try {
      const response = await apiClient.post<BudgetBackend>('/budgets', {
        name: request.name,
        description: request.description,
        period_type: request.periodType,
        year: request.year,
        quarter: request.quarter,
        month: request.month,
        start_date: request.startDate,
        end_date: request.endDate,
        warning_threshold: request.warningThreshold,
        critical_threshold: request.criticalThreshold,
        currency: request.currency,
        is_template: request.isTemplate,
        template_source_id: request.templateSourceId,
        notes: request.notes,
      });
      return transformBudget(response.data);
    } catch (error) {
      handleApiError(error, 'Budget erstellen');
    }
  },

  /**
   * Holt ein Budget
   */
  getBudget: async (budgetId: string, includeLines = true): Promise<Budget | null> => {
    try {
      const response = await apiClient.get<BudgetBackend>(
        `/budgets/${budgetId}?include_lines=${includeLines}`
      );
      return transformBudget(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return null;
      }
      handleApiError(error, 'Budget laden');
    }
  },

  /**
   * Listet Budgets auf
   */
  listBudgets: async (
    filter?: BudgetFilter,
    page = 0,
    pageSize = 20
  ): Promise<{ items: Budget[]; total: number; page: number; pageSize: number; totalPages: number }> => {
    try {
      const params = new URLSearchParams();
      params.append('page', String(page));
      params.append('page_size', String(pageSize));

      if (filter?.year) params.append('year', String(filter.year));
      if (filter?.periodType) params.append('period_type', filter.periodType);
      if (filter?.status) params.append('status', filter.status);
      if (filter?.isTemplate !== undefined) params.append('is_template', String(filter.isTemplate));
      if (filter?.search) params.append('search', filter.search);

      const response = await apiClient.get<BudgetListBackend>(`/budgets?${params.toString()}`);
      return {
        items: response.data.items.map(transformBudget),
        total: response.data.total,
        page: response.data.page,
        pageSize: response.data.page_size,
        totalPages: response.data.total_pages,
      };
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return { items: [], total: 0, page, pageSize, totalPages: 0 };
      }
      handleApiError(error, 'Budgets laden');
    }
  },

  /**
   * Holt Budget-Zusammenfassung
   */
  getBudgetSummary: async (budgetId: string): Promise<BudgetSummary | null> => {
    try {
      const response = await apiClient.get<BudgetSummaryBackend>(`/budgets/${budgetId}/summary`);
      return transformBudgetSummary(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return null;
      }
      handleApiError(error, 'Budget-Zusammenfassung laden');
    }
  },

  /**
   * Aktiviert ein Budget
   */
  activateBudget: async (budgetId: string): Promise<Budget> => {
    try {
      const response = await apiClient.post<BudgetBackend>(`/budgets/${budgetId}/activate`);
      return transformBudget(response.data);
    } catch (error) {
      handleApiError(error, 'Budget aktivieren');
    }
  },

  /**
   * Schließt ein Budget
   */
  closeBudget: async (budgetId: string): Promise<Budget> => {
    try {
      const response = await apiClient.post<BudgetBackend>(`/budgets/${budgetId}/close`);
      return transformBudget(response.data);
    } catch (error) {
      handleApiError(error, 'Budget schließen');
    }
  },

  // ==================== Budget Lines ====================

  /**
   * Erstellt eine Budget-Position
   */
  createBudgetLine: async (budgetId: string, request: BudgetLineCreateRequest): Promise<BudgetLine> => {
    try {
      const response = await apiClient.post<BudgetLineBackend>(`/budgets/${budgetId}/lines`, {
        kostenstelle_id: request.kostenstelleId,
        parent_line_id: request.parentLineId,
        category: request.category,
        subcategory: request.subcategory,
        planned_amount: request.plannedAmount,
        notes: request.notes,
        auto_assign_rules: request.autoAssignRules,
        sort_order: request.sortOrder,
      });
      return transformBudgetLine(response.data);
    } catch (error) {
      handleApiError(error, 'Budget-Position erstellen');
    }
  },

  /**
   * Listet Budget-Positionen
   */
  listBudgetLines: async (
    budgetId: string,
    kostenstelleId?: string,
    category?: string
  ): Promise<BudgetLine[]> => {
    try {
      const params = new URLSearchParams();
      if (kostenstelleId) params.append('kostenstelle_id', kostenstelleId);
      if (category) params.append('category', category);

      const url = `/budgets/${budgetId}/lines${params.toString() ? `?${params.toString()}` : ''}`;
      const response = await apiClient.get<BudgetLineBackend[]>(url);
      return response.data.map(transformBudgetLine);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Budget-Positionen laden');
    }
  },

  // ==================== Allocations ====================

  /**
   * Erstellt eine Zuweisung
   */
  createAllocation: async (budgetId: string, request: AllocationCreateRequest): Promise<BudgetAllocation> => {
    try {
      const response = await apiClient.post<BudgetAllocationBackend>(`/budgets/${budgetId}/allocations`, {
        budget_line_id: request.budgetLineId,
        document_id: request.documentId,
        amount: request.amount,
        source: request.source,
        description: request.description,
        ocr_confidence: request.ocrConfidence,
        ocr_extracted_category: request.ocrExtractedCategory,
        metadata: request.metadata,
      });
      return transformAllocation(response.data);
    } catch (error) {
      handleApiError(error, 'Zuweisung erstellen');
    }
  },

  /**
   * Listet Zuweisungen
   */
  listAllocations: async (
    budgetId: string,
    params?: {
      budgetLineId?: string;
      source?: AllocationSource;
      page?: number;
      pageSize?: number;
    }
  ): Promise<{ items: BudgetAllocation[]; total: number }> => {
    try {
      const queryParams = new URLSearchParams();
      if (params?.budgetLineId) queryParams.append('budget_line_id', params.budgetLineId);
      if (params?.source) queryParams.append('source', params.source);
      if (params?.page !== undefined) queryParams.append('page', String(params.page));
      if (params?.pageSize !== undefined) queryParams.append('page_size', String(params.pageSize));

      const url = `/budgets/${budgetId}/allocations${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
      const response = await apiClient.get<AllocationListBackend>(url);
      return {
        items: response.data.items.map(transformAllocation),
        total: response.data.total,
      };
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return { items: [], total: 0 };
      }
      handleApiError(error, 'Zuweisungen laden');
    }
  },

  // ==================== Variance Report ====================

  /**
   * Generiert Abweichungsbericht
   */
  getVarianceReport: async (budgetId: string): Promise<BudgetVarianceReport | null> => {
    try {
      const response = await apiClient.get<BudgetVarianceReportBackend>(
        `/budgets/${budgetId}/variance-report`
      );
      return transformVarianceReport(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return null;
      }
      handleApiError(error, 'Abweichungsbericht generieren');
    }
  },

  // ==================== Alerts ====================

  /**
   * Listet unbestätigte Alerts
   */
  listAlerts: async (params?: {
    budgetId?: string;
    severity?: AlertSeverity;
    acknowledgedOnly?: boolean;
  }): Promise<BudgetAlert[]> => {
    try {
      const queryParams = new URLSearchParams();
      if (params?.budgetId) queryParams.append('budget_id', params.budgetId);
      if (params?.severity) queryParams.append('severity', params.severity);
      if (params?.acknowledgedOnly !== undefined)
        queryParams.append('acknowledged_only', String(params.acknowledgedOnly));

      const url = `/budgets/alerts${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
      const response = await apiClient.get<BudgetAlertBackend[]>(url);
      return response.data.map(transformAlert);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Alerts laden');
    }
  },

  /**
   * Bestätigt einen Alert
   */
  acknowledgeAlert: async (alertId: string): Promise<BudgetAlert> => {
    try {
      const response = await apiClient.post<BudgetAlertBackend>(
        `/budgets/alerts/${alertId}/acknowledge`
      );
      return transformAlert(response.data);
    } catch (error) {
      handleApiError(error, 'Alert bestätigen');
    }
  },
};
