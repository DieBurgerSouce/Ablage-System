/**
 * ProactiveInsightsBanner - KI-gesteuerte Insights mit Aktionen
 *
 * Zeigt proaktive Hinweise und Empfehlungen:
 * - Optimierungs-Vorschläge
 * - Warnungen (z.B. überfällige Rechnungen)
 * - Chancen (z.B. Skonto-Möglichkeiten)
 * - Erinnerungen (z.B. bald fällig)
 *
 * Jeder Insight kann eine Aktion haben, die direkt ausgeführt werden kann.
 */

import { useState, useMemo, useCallback } from 'react';
import { Lightbulb, AlertTriangle, TrendingUp, Bell, X, ChevronRight, Sparkles, Loader2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { CategoryDocumentResponse, CategoryDocumentAggregations } from '../types';

// ==================== Types ====================

export type InsightType = 'optimization' | 'warning' | 'opportunity' | 'reminder';
export type InsightPriority = 'low' | 'medium' | 'high' | 'critical';

export interface ProactiveInsight {
  id: string;
  type: InsightType;
  priority: InsightPriority;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void | Promise<void>;
  };
  dismissible: boolean;
  documentIds?: string[];
}

interface ProactiveInsightsBannerProps {
  aggregations: CategoryDocumentAggregations | undefined;
  documents: CategoryDocumentResponse[];
  category: string;
  isLoading?: boolean;
  onMarkAsPaid?: (documentIds: string[]) => Promise<void>;
  onCreateReminders?: (documentIds: string[]) => Promise<void>;
  onFilterDocuments?: (filter: { paymentStatus?: string[] }) => void;
}

// ==================== Helper Functions ====================

/**
 * Formatiert einen Betrag als Währung (EUR)
 */
function formatCurrency(amount: number, currency = 'EUR'): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

/**
 * Berechnet das Alter einer Rechnung in Tagen
 */
function getInvoiceAge(dueDate: string | null): number {
  if (!dueDate) return 0;
  const due = new Date(dueDate);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);
  return Math.ceil((today.getTime() - due.getTime()) / (1000 * 60 * 60 * 24));
}

/**
 * Generiert Insights basierend auf Dokumenten und Aggregationen
 */
function generateInsights(
  documents: CategoryDocumentResponse[],
  aggregations: CategoryDocumentAggregations | undefined,
  category: string,
  actions: {
    onMarkAsPaid?: (ids: string[]) => Promise<void>;
    onCreateReminders?: (ids: string[]) => Promise<void>;
    onFilterDocuments?: (filter: { paymentStatus?: string[] }) => void;
  }
): ProactiveInsight[] {
  const insights: ProactiveInsight[] = [];

  // Nur für Rechnungen-bezogene Kategorien
  const isInvoiceCategory = ['rechnungen', 'offene_rechnungen', 'mahnungen'].includes(category);

  if (!isInvoiceCategory || !aggregations) {
    return insights;
  }

  // 1. Überfällige Rechnungen (kritisch)
  const overdueCount = aggregations.overdueCount || 0;
  const overdueAmount = aggregations.totalOverdue || 0;
  const overdueDocuments = documents.filter((d) => d.paymentStatus === 'überfällig');
  const oldestOverdue = overdueDocuments.reduce(
    (oldest, doc) => {
      const age = getInvoiceAge(doc.dueDate);
      return age > oldest.age ? { age, doc } : oldest;
    },
    { age: 0, doc: null as CategoryDocumentResponse | null }
  );

  if (overdueCount > 0) {
    insights.push({
      id: 'overdue-invoices',
      type: 'warning',
      priority: 'critical',
      title: `${overdueCount} Rechnung${overdueCount > 1 ? 'en' : ''} überfällig`,
      description: `Gesamt: ${formatCurrency(overdueAmount)}${oldestOverdue.age > 0 ? ` - Älteste: ${oldestOverdue.age} Tage` : ''}`,
      action: actions.onCreateReminders
        ? {
            label: 'Mahnungen erstellen',
            onClick: () => actions.onCreateReminders!(overdueDocuments.map((d) => d.id)),
          }
        : undefined,
      dismissible: false,
      documentIds: overdueDocuments.map((d) => d.id),
    });
  }

  // 2. Bald fällige Rechnungen (Erinnerung)
  const dueSoonDocuments = documents.filter((d) => {
    if (d.paymentStatus !== 'offen' || !d.dueDate) return false;
    const daysUntil = -getInvoiceAge(d.dueDate); // Negativ = noch nicht fällig
    return daysUntil > 0 && daysUntil <= 7;
  });
  const dueSoonAmount = dueSoonDocuments.reduce((sum, d) => sum + (d.totalAmount || 0), 0);

  if (dueSoonDocuments.length > 0) {
    insights.push({
      id: 'due-soon',
      type: 'reminder',
      priority: 'medium',
      title: `${dueSoonDocuments.length} Rechnung${dueSoonDocuments.length > 1 ? 'en' : ''} bald fällig`,
      description: `${formatCurrency(dueSoonAmount)} in den nächsten 7 Tagen`,
      action: actions.onFilterDocuments
        ? {
            label: 'Anzeigen',
            onClick: () => actions.onFilterDocuments!({ paymentStatus: ['offen'] }),
          }
        : undefined,
      dismissible: true,
      documentIds: dueSoonDocuments.map((d) => d.id),
    });
  }

  // 3. Skonto-Möglichkeit (Chance)
  // Simuliert: Rechnungen mit > 5 Tagen bis Fälligkeit können Skonto haben
  const skontoDocuments = documents.filter((d) => {
    if (d.paymentStatus !== 'offen' || !d.dueDate) return false;
    const daysUntil = -getInvoiceAge(d.dueDate);
    return daysUntil > 5 && daysUntil <= 14;
  });
  const potentialSaving = skontoDocuments.reduce((sum, d) => sum + (d.totalAmount || 0) * 0.02, 0);

  if (skontoDocuments.length > 0 && potentialSaving > 10) {
    insights.push({
      id: 'skonto-opportunity',
      type: 'opportunity',
      priority: 'low',
      title: 'Skonto-Potenzial',
      description: `${skontoDocuments.length} Rechnung${skontoDocuments.length > 1 ? 'en' : ''} mit moegl. ${formatCurrency(potentialSaving)} Ersparnis`,
      action: actions.onMarkAsPaid
        ? {
            label: 'Als bezahlt markieren',
            onClick: () => actions.onMarkAsPaid!(skontoDocuments.slice(0, 1).map((d) => d.id)),
          }
        : undefined,
      dismissible: true,
      documentIds: skontoDocuments.map((d) => d.id),
    });
  }

  // 4. Verarbeitungsfehler (Warnung)
  const failedDocuments = documents.filter((d) => d.processingStatus === 'failed');
  if (failedDocuments.length > 0) {
    insights.push({
      id: 'processing-failed',
      type: 'warning',
      priority: 'high',
      title: `${failedDocuments.length} Dokument${failedDocuments.length > 1 ? 'e' : ''} mit Fehlern`,
      description: 'OCR-Verarbeitung fehlgeschlagen - manuelle Prüfung erforderlich',
      dismissible: true,
      documentIds: failedDocuments.map((d) => d.id),
    });
  }

  // Sortiere nach Priorität
  const priorityOrder: Record<InsightPriority, number> = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
  };
  insights.sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]);

  return insights;
}

// ==================== Sub-Components ====================

const insightConfig: Record<InsightType, { icon: React.ElementType; color: string; bgColor: string }> = {
  optimization: {
    icon: Lightbulb,
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
  },
  warning: {
    icon: AlertTriangle,
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
  },
  opportunity: {
    icon: TrendingUp,
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
  },
  reminder: {
    icon: Bell,
    color: 'text-yellow-600 dark:text-yellow-400',
    bgColor: 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800',
  },
};

function InsightCard({
  insight,
  onDismiss,
  isExecuting,
}: {
  insight: ProactiveInsight;
  onDismiss?: (id: string) => void;
  isExecuting?: boolean;
}) {
  const [isActionLoading, setIsActionLoading] = useState(false);
  const config = insightConfig[insight.type];
  const Icon = config.icon;

  const handleAction = useCallback(async () => {
    if (!insight.action || isActionLoading) return;
    setIsActionLoading(true);
    try {
      await insight.action.onClick();
    } finally {
      setIsActionLoading(false);
    }
  }, [insight.action, isActionLoading]);

  return (
    <div
      className={cn(
        'flex items-start gap-3 p-3 rounded-lg border transition-all',
        config.bgColor,
        insight.priority === 'critical' && 'ring-2 ring-red-500'
      )}
    >
      {/* Icon */}
      <div className={cn('p-1.5 rounded-full bg-white dark:bg-gray-800', config.color)}>
        <Icon className="w-4 h-4" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className={cn('text-sm font-medium', config.color)}>{insight.title}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{insight.description}</p>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {insight.action && (
          <Button
            size="sm"
            variant="ghost"
            onClick={handleAction}
            disabled={isActionLoading || isExecuting}
            className={cn('text-xs h-7', config.color)}
          >
            {isActionLoading ? (
              <Loader2 className="w-3 h-3 animate-spin mr-1" />
            ) : (
              <ChevronRight className="w-3 h-3 mr-1" />
            )}
            {insight.action.label}
          </Button>
        )}
        {insight.dismissible && onDismiss && (
          <Button
            size="icon"
            variant="ghost"
            onClick={() => onDismiss(insight.id)}
            className="h-6 w-6 opacity-50 hover:opacity-100"
          >
            <X className="w-3 h-3" />
          </Button>
        )}
      </div>
    </div>
  );
}

// ==================== Main Component ====================

export function ProactiveInsightsBanner({
  aggregations,
  documents,
  category,
  isLoading,
  onMarkAsPaid,
  onCreateReminders,
  onFilterDocuments,
}: ProactiveInsightsBannerProps) {
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const [isExecuting, setIsExecuting] = useState(false);

  // Generiere Insights
  const insights = useMemo(
    () =>
      generateInsights(documents, aggregations, category, {
        onMarkAsPaid,
        onCreateReminders,
        onFilterDocuments,
      }),
    [documents, aggregations, category, onMarkAsPaid, onCreateReminders, onFilterDocuments]
  );

  // Filtere dismissed Insights
  const visibleInsights = useMemo(
    () => insights.filter((i) => !dismissedIds.has(i.id)),
    [insights, dismissedIds]
  );

  const handleDismiss = useCallback((id: string) => {
    setDismissedIds((prev) => new Set([...prev, id]));
  }, []);

  // Loading oder keine Insights
  if (isLoading || visibleInsights.length === 0) {
    return null;
  }

  return (
    <Card data-testid="proactive-insights-banner" className="border-l-4 border-l-purple-500 bg-gradient-to-r from-purple-50/50 to-transparent dark:from-purple-900/10">
      <CardContent className="p-4">
        {/* Header */}
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-4 h-4 text-purple-500" />
          <span className="text-sm font-medium text-purple-700 dark:text-purple-300">
            KI-Insights
          </span>
          <span className="text-xs text-muted-foreground">
            ({visibleInsights.length} Hinweis{visibleInsights.length > 1 ? 'e' : ''})
          </span>
        </div>

        {/* Insights Grid */}
        <div className="space-y-2">
          {visibleInsights.map((insight) => (
            <InsightCard
              key={insight.id}
              insight={insight}
              onDismiss={handleDismiss}
              isExecuting={isExecuting}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export default ProactiveInsightsBanner;
