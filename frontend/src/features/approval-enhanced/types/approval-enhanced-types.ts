/**
 * Types for Approval Enhanced feature
 * Backend uses snake_case, Frontend uses camelCase
 */

// ==================== Backend Types (snake_case) ====================

export interface ConditionalRuleBackend {
  id: number;
  name: string;
  conditions: Record<string, unknown>;
  actions: Record<string, unknown>;
  priority: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EscalationRuleBackend {
  id: number;
  name: string;
  timeout_hours: number;
  escalation_target: string;
  notify_original: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SubstitutionRuleBackend {
  id: number;
  original_user_id: number;
  substitute_user_id: number;
  start_date: string;
  end_date: string;
  scope: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SLAMetricsBackend {
  avg_approval_time_hours: number;
  sla_breach_count: number;
  total_approvals: number;
  pending_count: number;
  bottleneck_stages: Array<{
    stage: string;
    avg_duration_hours: number;
    count: number;
  }>;
}

export interface SLAReportBackend {
  period_start: string;
  period_end: string;
  total_documents: number;
  breaches: number;
  breach_rate: number;
  avg_approval_time_hours: number;
  slowest_stages: Array<{
    stage: string;
    avg_duration_hours: number;
  }>;
}

export interface AutoFileStatsBackend {
  total_filed: number;
  success_rate: number;
  last_run: string;
  rules_count: number;
}

export interface AutoMatchResultBackend {
  document_id: number;
  matched_entities: Array<{
    entity_type: string;
    entity_id: number;
    confidence: number;
  }>;
  confidence_score: number;
}

// ==================== Frontend Types (camelCase) ====================

export interface ConditionalRule {
  id: number;
  name: string;
  conditions: Record<string, unknown>;
  actions: Record<string, unknown>;
  priority: number;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface EscalationRule {
  id: number;
  name: string;
  timeoutHours: number;
  escalationTarget: string;
  notifyOriginal: boolean;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface SubstitutionRule {
  id: number;
  originalUserId: number;
  substituteUserId: number;
  startDate: string;
  endDate: string;
  scope: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface SLAMetrics {
  avgApprovalTimeHours: number;
  slaBreachCount: number;
  totalApprovals: number;
  pendingCount: number;
  bottleneckStages: Array<{
    stage: string;
    avgDurationHours: number;
    count: number;
  }>;
}

export interface SLAReport {
  periodStart: string;
  periodEnd: string;
  totalDocuments: number;
  breaches: number;
  breachRate: number;
  avgApprovalTimeHours: number;
  slowestStages: Array<{
    stage: string;
    avgDurationHours: number;
  }>;
}

export interface AutoFileStats {
  totalFiled: number;
  successRate: number;
  lastRun: string;
  rulesCount: number;
}

export interface AutoMatchResult {
  documentId: number;
  matchedEntities: Array<{
    entityType: string;
    entityId: number;
    confidence: number;
  }>;
  confidenceScore: number;
}

// ==================== Create/Update DTOs ====================

export interface CreateConditionalRuleDTO {
  name: string;
  conditions: Record<string, unknown>;
  actions: Record<string, unknown>;
  priority: number;
  is_active: boolean;
}

export interface UpdateConditionalRuleDTO {
  name?: string;
  conditions?: Record<string, unknown>;
  actions?: Record<string, unknown>;
  priority?: number;
  is_active?: boolean;
}

export interface CreateEscalationRuleDTO {
  name: string;
  timeout_hours: number;
  escalation_target: string;
  notify_original: boolean;
}

export interface CreateSubstitutionRuleDTO {
  original_user_id: number;
  substitute_user_id: number;
  start_date: string;
  end_date: string;
  scope: string;
}

// ==================== Transforms ====================

export function transformConditionalRule(backend: ConditionalRuleBackend): ConditionalRule {
  return {
    id: backend.id,
    name: backend.name,
    conditions: backend.conditions,
    actions: backend.actions,
    priority: backend.priority,
    isActive: backend.is_active,
    createdAt: backend.created_at,
    updatedAt: backend.updated_at,
  };
}

export function transformEscalationRule(backend: EscalationRuleBackend): EscalationRule {
  return {
    id: backend.id,
    name: backend.name,
    timeoutHours: backend.timeout_hours,
    escalationTarget: backend.escalation_target,
    notifyOriginal: backend.notify_original,
    isActive: backend.is_active,
    createdAt: backend.created_at,
    updatedAt: backend.updated_at,
  };
}

export function transformSubstitutionRule(backend: SubstitutionRuleBackend): SubstitutionRule {
  return {
    id: backend.id,
    originalUserId: backend.original_user_id,
    substituteUserId: backend.substitute_user_id,
    startDate: backend.start_date,
    endDate: backend.end_date,
    scope: backend.scope,
    isActive: backend.is_active,
    createdAt: backend.created_at,
    updatedAt: backend.updated_at,
  };
}

export function transformSLAMetrics(backend: SLAMetricsBackend): SLAMetrics {
  return {
    avgApprovalTimeHours: backend.avg_approval_time_hours,
    slaBreachCount: backend.sla_breach_count,
    totalApprovals: backend.total_approvals,
    pendingCount: backend.pending_count,
    bottleneckStages: backend.bottleneck_stages.map(stage => ({
      stage: stage.stage,
      avgDurationHours: stage.avg_duration_hours,
      count: stage.count,
    })),
  };
}

export function transformSLAReport(backend: SLAReportBackend): SLAReport {
  return {
    periodStart: backend.period_start,
    periodEnd: backend.period_end,
    totalDocuments: backend.total_documents,
    breaches: backend.breaches,
    breachRate: backend.breach_rate,
    avgApprovalTimeHours: backend.avg_approval_time_hours,
    slowestStages: backend.slowest_stages.map(stage => ({
      stage: stage.stage,
      avgDurationHours: stage.avg_duration_hours,
    })),
  };
}

export function transformAutoFileStats(backend: AutoFileStatsBackend): AutoFileStats {
  return {
    totalFiled: backend.total_filed,
    successRate: backend.success_rate,
    lastRun: backend.last_run,
    rulesCount: backend.rules_count,
  };
}

export function transformAutoMatchResult(backend: AutoMatchResultBackend): AutoMatchResult {
  return {
    documentId: backend.document_id,
    matchedEntities: backend.matched_entities.map(entity => ({
      entityType: entity.entity_type,
      entityId: entity.entity_id,
      confidence: entity.confidence,
    })),
    confidenceScore: backend.confidence_score,
  };
}

// ==================== UI Labels (German) ====================

export const UI_LABELS = {
  conditionalRules: {
    title: 'Bedingte Regeln',
    createNew: 'Neue Regel erstellen',
    edit: 'Regel bearbeiten',
    delete: 'Regel löschen',
    name: 'Regelname',
    conditions: 'Bedingungen',
    actions: 'Aktionen',
    priority: 'Priorität',
    isActive: 'Aktiv',
    noRules: 'Keine bedingten Regeln vorhanden',
  },
  escalationRules: {
    title: 'Eskalationsregeln',
    createNew: 'Neue Eskalationsregel erstellen',
    delete: 'Eskalationsregel löschen',
    name: 'Regelname',
    timeoutHours: 'Timeout (Stunden)',
    escalationTarget: 'Eskalationsziel',
    notifyOriginal: 'Ursprünglichen Genehmiger benachrichtigen',
    noRules: 'Keine Eskalationsregeln vorhanden',
  },
  substitutionRules: {
    title: 'Stellvertretung',
    createNew: 'Neue Stellvertretung erstellen',
    delete: 'Stellvertretung löschen',
    originalUser: 'Benutzer',
    substituteUser: 'Stellvertreter',
    startDate: 'Startdatum',
    endDate: 'Enddatum',
    scope: 'Geltungsbereich',
    noRules: 'Keine Stellvertretungen vorhanden',
  },
  sla: {
    title: 'SLA-Dashboard',
    subtitle: 'Service-Level-Überwachung für Genehmigungsprozesse',
    avgApprovalTime: 'Durchschn. Genehmigungszeit',
    breachCount: 'SLA-Verstöße',
    totalApprovals: 'Genehmigungen gesamt',
    pendingCount: 'Ausstehend',
    bottleneckStages: 'Engpass-Phasen',
    hours: 'Stunden',
    report: 'SLA-Bericht',
  },
  autoFile: {
    title: 'Automatische Ablage',
    totalFiled: 'Abgelegte Dokumente',
    successRate: 'Erfolgsquote',
    lastRun: 'Letzte Ausführung',
    rulesCount: 'Anzahl Regeln',
    trigger: 'Ablage auslösen',
  },
  autoMatch: {
    title: 'Automatische Zuordnung',
    trigger: 'Zuordnung auslösen',
    results: 'Zuordnungsergebnisse',
    confidence: 'Konfidenz',
  },
  common: {
    save: 'Speichern',
    cancel: 'Abbrechen',
    delete: 'Löschen',
    edit: 'Bearbeiten',
    create: 'Erstellen',
    actions: 'Aktionen',
    loading: 'Lädt...',
    error: 'Fehler',
    success: 'Erfolgreich',
  },
} as const;

// ==================== Condition/Action Types ====================

export type ConditionOperator = 'equals' | 'greater_than' | 'less_than' | 'contains' | 'not_equals';
export type ConditionField = 'amount' | 'document_type' | 'entity_id' | 'tag';
export type ActionType = 'add_approver' | 'auto_approve' | 'auto_reject' | 'notify';

export interface Condition {
  field: ConditionField;
  operator: ConditionOperator;
  value: string | number;
}

export interface Action {
  type: ActionType;
  parameters: Record<string, unknown>;
}

export const CONDITION_OPERATORS: Record<ConditionOperator, string> = {
  equals: 'gleich',
  greater_than: 'größer als',
  less_than: 'kleiner als',
  contains: 'enthält',
  not_equals: 'ungleich',
};

export const CONDITION_FIELDS: Record<ConditionField, string> = {
  amount: 'Betrag',
  document_type: 'Dokumenttyp',
  entity_id: 'Entitäts-ID',
  tag: 'Tag',
};

export const ACTION_TYPES: Record<ActionType, string> = {
  add_approver: 'Zusätzlicher Genehmiger',
  auto_approve: 'Automatisch genehmigen',
  auto_reject: 'Automatisch ablehnen',
  notify: 'Benachrichtigung senden',
};
