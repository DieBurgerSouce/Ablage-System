/**
 * InsightCard - Displays a proactive insight from the Finance Assistant
 *
 * Vision 2.0 - Phase 1 (Januar 2026)
 */

import { motion } from 'framer-motion';
import {
  Clock,
  DollarSign,
  Percent,
  AlertTriangle,
  TrendingUp,
  Shield,
  Star,
  ExternalLink,
  ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { type InsightResponse, InsightCategory, InsightSeverity, SEVERITY_METADATA, CATEGORY_METADATA } from '@/lib/api/services/finance-assistant';
import { useNavigate } from '@tanstack/react-router';

interface InsightCardProps {
  insight: InsightResponse;
  onDismiss?: () => void;
  compact?: boolean;
  className?: string;
}

const CATEGORY_ICONS: Record<InsightCategory, typeof Clock> = {
  [InsightCategory.OVERDUE]: Clock,
  [InsightCategory.CASHFLOW]: DollarSign,
  [InsightCategory.SKONTO]: Percent,
  [InsightCategory.ANOMALY]: AlertTriangle,
  [InsightCategory.TREND]: TrendingUp,
  [InsightCategory.RISK]: Shield,
  [InsightCategory.OPPORTUNITY]: Star,
};

const SEVERITY_COLORS: Record<InsightSeverity, string> = {
  [InsightSeverity.INFO]: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  [InsightSeverity.LOW]: 'bg-green-500/10 text-green-500 border-green-500/20',
  [InsightSeverity.MEDIUM]: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  [InsightSeverity.HIGH]: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  [InsightSeverity.CRITICAL]: 'bg-red-500/10 text-red-500 border-red-500/20',
};

export function InsightCard({ insight, onDismiss, compact = false, className }: InsightCardProps) {
  const navigate = useNavigate();
  const categoryMeta = CATEGORY_METADATA[insight.category as InsightCategory];
  const severityMeta = SEVERITY_METADATA[insight.severity as InsightSeverity];
  const CategoryIcon = CATEGORY_ICONS[insight.category as InsightCategory] || AlertTriangle;

  const handleNavigate = () => {
    if (insight.action_url) {
      navigate({ to: insight.action_url });
    }
  };

  if (compact) {
    return (
      <motion.div
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        className={cn(
          'flex items-center gap-3 rounded-lg border p-3 hover:bg-muted/50 cursor-pointer transition-colors',
          SEVERITY_COLORS[insight.severity as InsightSeverity],
          className
        )}
        onClick={handleNavigate}
      >
        <CategoryIcon className="h-4 w-4 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{insight.title}</p>
          <p className="text-xs text-muted-foreground truncate">{insight.summary}</p>
        </div>
        <ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={cn(
        'rounded-lg border bg-card p-4 shadow-sm',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'rounded-full p-2',
            SEVERITY_COLORS[insight.severity as InsightSeverity]
          )}
        >
          <CategoryIcon className="h-4 w-4" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h4 className="font-medium">{insight.title}</h4>
            <Badge variant="outline" className="text-xs">
              {categoryMeta?.label || insight.category}
            </Badge>
            <Badge
              variant="outline"
              className={cn('text-xs', SEVERITY_COLORS[insight.severity as InsightSeverity])}
            >
              {severityMeta?.label || insight.severity}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{insight.summary}</p>
        </div>
      </div>

      {/* Details */}
      <div className="mt-3 text-sm text-muted-foreground">
        {insight.details}
      </div>

      {/* Metrics */}
      {Object.keys(insight.metrics).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-3">
          {Object.entries(insight.metrics).map(([key, value]) => (
            <div key={key} className="rounded-md bg-muted px-3 py-1.5">
              <div className="text-xs text-muted-foreground">{formatMetricKey(key)}</div>
              <div className="font-medium">{formatMetricValue(value)}</div>
            </div>
          ))}
        </div>
      )}

      {/* Recommendations */}
      {insight.recommendations.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-medium text-muted-foreground mb-2">Empfehlungen:</div>
          <ul className="space-y-1">
            {insight.recommendations.map((rec, index) => (
              <li key={index} className="flex items-start gap-2 text-sm">
                <ChevronRight className="h-4 w-4 flex-shrink-0 text-primary mt-0.5" />
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Affected Entities */}
      {insight.affected_entities.length > 0 && (
        <div className="mt-3 text-xs text-muted-foreground">
          {insight.affected_entities.length} betroffene Entitäten
        </div>
      )}

      {/* Actions */}
      <div className="mt-4 flex items-center gap-2">
        {insight.action_url && (
          <Button size="sm" onClick={handleNavigate}>
            <ExternalLink className="mr-2 h-4 w-4" />
            Details anzeigen
          </Button>
        )}
        {onDismiss && (
          <Button variant="outline" size="sm" onClick={onDismiss}>
            Schließen
          </Button>
        )}
      </div>
    </motion.div>
  );
}

// ===== Helper Functions =====

function formatMetricKey(key: string): string {
  const labels: Record<string, string> = {
    total_amount: 'Gesamtbetrag',
    count: 'Anzahl',
    average: 'Durchschnitt',
    days_overdue: 'Tage überfällig',
    potential_savings: 'Mögliche Ersparnis',
    risk_score: 'Risiko-Score',
    trend_percentage: 'Trend',
  };
  return labels[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatMetricValue(value: unknown): string {
  if (typeof value === 'number') {
    if (value >= 1000) {
      return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
        maximumFractionDigits: 0,
      }).format(value);
    }
    if (value < 1 && value > 0) {
      return `${Math.round(value * 100)}%`;
    }
    return new Intl.NumberFormat('de-DE').format(value);
  }
  return String(value);
}

// ===== Insights List Component =====

interface InsightsListProps {
  insights: InsightResponse[];
  maxItems?: number;
  compact?: boolean;
  showEmpty?: boolean;
  onViewAll?: () => void;
  className?: string;
}

export function InsightsList({
  insights,
  maxItems = 5,
  compact = false,
  showEmpty = true,
  onViewAll,
  className,
}: InsightsListProps) {
  const displayInsights = maxItems ? insights.slice(0, maxItems) : insights;
  const hasMore = insights.length > displayInsights.length;

  if (insights.length === 0 && showEmpty) {
    return (
      <div className={cn('text-center py-8 text-muted-foreground', className)}>
        <Star className="h-8 w-8 mx-auto mb-2 opacity-50" />
        <p className="text-sm">Keine Insights verfügbar</p>
      </div>
    );
  }

  return (
    <div className={cn('space-y-3', className)}>
      {displayInsights.map((insight) => (
        <InsightCard key={insight.id} insight={insight} compact={compact} />
      ))}
      {hasMore && onViewAll && (
        <Button variant="ghost" className="w-full" onClick={onViewAll}>
          Alle {insights.length} Insights anzeigen
          <ChevronRight className="ml-2 h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
