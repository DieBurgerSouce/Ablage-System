// Proactive Assistant Types - Backend & Frontend with Transform Functions

// ============================================================================
// Backend Response Types (snake_case - matching Python API)
// ============================================================================

export type HintCategory = 'fristen' | 'anomalien' | 'optimierung';
export type HintPriority = 'low' | 'medium' | 'high' | 'critical';
export type HintStatus = 'new' | 'seen' | 'confirmed' | 'dismissed' | 'acted';

export interface HintResponse {
  hint_id: string;
  category: HintCategory;
  priority: HintPriority;
  status: HintStatus;
  title: string;
  description: string;
  context: Record<string, unknown>;
  entity_type?: string;
  entity_id?: string;
  created_at: string;
  updated_at: string;
  action_url?: string;
  recommended_action?: string;
}

export interface DashboardSummaryResponse {
  total_hints: number;
  by_category: {
    fristen: number;
    anomalien: number;
    optimierung: number;
  };
  by_priority: {
    low: number;
    medium: number;
    high: number;
    critical: number;
  };
  by_status: {
    new: number;
    seen: number;
    confirmed: number;
    dismissed: number;
    acted: number;
  };
}

export interface HintListResponse {
  hints: HintResponse[];
  total_count: number;
  limit: number;
  offset: number;
}

export interface StatisticsResponse {
  total_generated: number;
  total_acted: number;
  total_dismissed: number;
  action_rate: number;
  dismiss_rate: number;
  by_category: {
    fristen: {
      generated: number;
      acted: number;
      dismissed: number;
    };
    anomalien: {
      generated: number;
      acted: number;
      dismissed: number;
    };
    optimierung: {
      generated: number;
      acted: number;
      dismissed: number;
    };
  };
}

export interface HintRuleResponse {
  rule_id: string;
  name: string;
  category: HintCategory;
  enabled: boolean;
  conditions: Record<string, unknown>;
  template: string;
  priority: HintPriority;
  created_at: string;
  updated_at: string;
}

// ============================================================================
// Frontend Types (camelCase - used in components)
// ============================================================================

export interface Hint {
  hintId: string;
  category: HintCategory;
  priority: HintPriority;
  status: HintStatus;
  title: string;
  description: string;
  context: Record<string, unknown>;
  entityType?: string;
  entityId?: string;
  createdAt: Date;
  updatedAt: Date;
  actionUrl?: string;
  recommendedAction?: string;
}

export interface DashboardSummary {
  totalHints: number;
  byCategory: {
    fristen: number;
    anomalien: number;
    optimierung: number;
  };
  byPriority: {
    low: number;
    medium: number;
    high: number;
    critical: number;
  };
  byStatus: {
    new: number;
    seen: number;
    confirmed: number;
    dismissed: number;
    acted: number;
  };
}

export interface HintList {
  hints: Hint[];
  totalCount: number;
  limit: number;
  offset: number;
}

export interface Statistics {
  totalGenerated: number;
  totalActed: number;
  totalDismissed: number;
  actionRate: number;
  dismissRate: number;
  byCategory: {
    fristen: {
      generated: number;
      acted: number;
      dismissed: number;
    };
    anomalien: {
      generated: number;
      acted: number;
      dismissed: number;
    };
    optimierung: {
      generated: number;
      acted: number;
      dismissed: number;
    };
  };
}

export interface HintRule {
  ruleId: string;
  name: string;
  category: HintCategory;
  enabled: boolean;
  conditions: Record<string, unknown>;
  template: string;
  priority: HintPriority;
  createdAt: Date;
  updatedAt: Date;
}

// ============================================================================
// Transform Functions
// ============================================================================

export function transformHint(response: HintResponse): Hint {
  return {
    hintId: response.hint_id,
    category: response.category,
    priority: response.priority,
    status: response.status,
    title: response.title,
    description: response.description,
    context: response.context,
    entityType: response.entity_type,
    entityId: response.entity_id,
    createdAt: new Date(response.created_at),
    updatedAt: new Date(response.updated_at),
    actionUrl: response.action_url,
    recommendedAction: response.recommended_action,
  };
}

export function transformDashboardSummary(response: DashboardSummaryResponse): DashboardSummary {
  return {
    totalHints: response.total_hints,
    byCategory: response.by_category,
    byPriority: response.by_priority,
    byStatus: response.by_status,
  };
}

export function transformHintList(response: HintListResponse): HintList {
  return {
    hints: response.hints.map(transformHint),
    totalCount: response.total_count,
    limit: response.limit,
    offset: response.offset,
  };
}

export function transformStatistics(response: StatisticsResponse): Statistics {
  return {
    totalGenerated: response.total_generated,
    totalActed: response.total_acted,
    totalDismissed: response.total_dismissed,
    actionRate: response.action_rate,
    dismissRate: response.dismiss_rate,
    byCategory: response.by_category,
  };
}

export function transformHintRule(response: HintRuleResponse): HintRule {
  return {
    ruleId: response.rule_id,
    name: response.name,
    category: response.category,
    enabled: response.enabled,
    conditions: response.conditions,
    template: response.template,
    priority: response.priority,
    createdAt: new Date(response.created_at),
    updatedAt: new Date(response.updated_at),
  };
}

// ============================================================================
// UI Labels & Constants
// ============================================================================

export const UI_LABELS = {
  // Page titles
  pageTitle: 'Proaktiver Assistent',
  pageSubtitle: 'Intelligente Hinweise und Empfehlungen',
  rulesPageTitle: 'Hinweis-Regeln',
  rulesPageSubtitle: 'Konfiguration der automatischen Hinweisgenerierung',

  // Categories
  categories: {
    fristen: 'Fristen',
    anomalien: 'Anomalien',
    optimierung: 'Optimierung',
  },

  // Priorities
  priorities: {
    low: 'Niedrig',
    medium: 'Mittel',
    high: 'Hoch',
    critical: 'Kritisch',
  },

  // Statuses
  statuses: {
    new: 'Neu',
    seen: 'Gesehen',
    confirmed: 'Bestätigt',
    dismissed: 'Abgelehnt',
    acted: 'Umgesetzt',
  },

  // Actions
  actions: {
    accept: 'Annehmen',
    dismiss: 'Ablehnen',
    defer: 'Zurückstellen',
    viewDetails: 'Details anzeigen',
    markAsSeen: 'Als gesehen markieren',
    markAsActed: 'Als umgesetzt markieren',
    generateHints: 'Hinweise generieren',
    retry: 'Erneut versuchen',
  },

  // Filters
  filters: {
    all: 'Alle',
    category: 'Kategorie',
    priority: 'Priorität',
    status: 'Status',
  },

  // Statistics
  statistics: {
    generated: 'Generiert',
    acted: 'Umgesetzt',
    dismissed: 'Abgelehnt',
    actionRate: 'Umsetzungsrate',
    dismissRate: 'Ablehnungsrate',
  },

  // Messages
  messages: {
    noHints: 'Keine Hinweise verfügbar',
    noContextHints: 'Keine kontextbezogenen Hinweise',
    loadingDashboard: 'Dashboard wird geladen...',
    loadingHints: 'Hinweise werden geladen...',
    errorLoadingDashboard: 'Fehler beim Laden des Dashboards',
    errorLoadingHints: 'Fehler beim Laden der Hinweise',
    errorUpdatingStatus: 'Fehler beim Aktualisieren des Status',
    statusUpdated: 'Status erfolgreich aktualisiert',
    generatingHints: 'Hinweise werden generiert...',
    hintsGenerated: 'Hinweise erfolgreich generiert',
    errorGeneratingHints: 'Fehler beim Generieren der Hinweise',
  },
} as const;

// ============================================================================
// Category Configuration
// ============================================================================

export const CATEGORY_CONFIG = {
  fristen: {
    label: UI_LABELS.categories.fristen,
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
    icon: '📅',
  },
  anomalien: {
    label: UI_LABELS.categories.anomalien,
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    icon: '⚠️',
  },
  optimierung: {
    label: UI_LABELS.categories.optimierung,
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
    icon: '💡',
  },
} as const;

// ============================================================================
// Priority Configuration
// ============================================================================

export const PRIORITY_CONFIG = {
  low: {
    label: UI_LABELS.priorities.low,
    color: 'text-gray-600',
    bgColor: 'bg-gray-100',
    variant: 'secondary' as const,
  },
  medium: {
    label: UI_LABELS.priorities.medium,
    color: 'text-blue-600',
    bgColor: 'bg-blue-100',
    variant: 'default' as const,
  },
  high: {
    label: UI_LABELS.priorities.high,
    color: 'text-orange-600',
    bgColor: 'bg-orange-100',
    variant: 'default' as const,
  },
  critical: {
    label: UI_LABELS.priorities.critical,
    color: 'text-red-600',
    bgColor: 'bg-red-100',
    variant: 'destructive' as const,
  },
} as const;

// ============================================================================
// Status Configuration
// ============================================================================

export const STATUS_CONFIG = {
  new: {
    label: UI_LABELS.statuses.new,
    color: 'text-blue-600',
    bgColor: 'bg-blue-100',
    variant: 'default' as const,
  },
  seen: {
    label: UI_LABELS.statuses.seen,
    color: 'text-gray-600',
    bgColor: 'bg-gray-100',
    variant: 'secondary' as const,
  },
  confirmed: {
    label: UI_LABELS.statuses.confirmed,
    color: 'text-purple-600',
    bgColor: 'bg-purple-100',
    variant: 'default' as const,
  },
  dismissed: {
    label: UI_LABELS.statuses.dismissed,
    color: 'text-gray-500',
    bgColor: 'bg-gray-50',
    variant: 'outline' as const,
  },
  acted: {
    label: UI_LABELS.statuses.acted,
    color: 'text-green-600',
    bgColor: 'bg-green-100',
    variant: 'default' as const,
  },
} as const;
