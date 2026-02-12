/**
 * InsightsWidget - Dashboard widget for proactive Finance Assistant insights
 *
 * Vision 2.0 - Phase 1 (Januar 2026)
 *
 * Displays a compact list of insights that can be expanded.
 * Designed to be embedded in the main dashboard.
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Lightbulb,
  RefreshCw,
  ChevronRight,
  AlertTriangle,
  TrendingUp,
  Clock,
  DollarSign,
  Loader2,
  Sparkles,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { useInsights } from '../hooks/use-finance-assistant';
import {
  InsightResponse,
  InsightCategory,
  InsightSeverity,
  SEVERITY_METADATA,
  CATEGORY_METADATA,
} from '@/lib/api/services/finance-assistant';
import { useNavigate } from '@tanstack/react-router';

const SEVERITY_COLORS: Record<InsightSeverity, string> = {
  [InsightSeverity.INFO]: 'text-blue-500 bg-blue-500/10',
  [InsightSeverity.LOW]: 'text-green-500 bg-green-500/10',
  [InsightSeverity.MEDIUM]: 'text-yellow-500 bg-yellow-500/10',
  [InsightSeverity.HIGH]: 'text-orange-500 bg-orange-500/10',
  [InsightSeverity.CRITICAL]: 'text-red-500 bg-red-500/10',
};

const CATEGORY_ICONS: Record<InsightCategory, typeof Clock> = {
  [InsightCategory.OVERDUE]: Clock,
  [InsightCategory.CASHFLOW]: DollarSign,
  [InsightCategory.SKONTO]: DollarSign,
  [InsightCategory.ANOMALY]: AlertTriangle,
  [InsightCategory.TREND]: TrendingUp,
  [InsightCategory.RISK]: AlertTriangle,
  [InsightCategory.OPPORTUNITY]: Sparkles,
};

interface InsightsWidgetProps {
  maxItems?: number;
  showRefresh?: boolean;
  className?: string;
}

export function InsightsWidget({
  maxItems = 5,
  showRefresh = true,
  className,
}: InsightsWidgetProps) {
  const navigate = useNavigate();
  const { data, isLoading, error, refetch, isFetching } = useInsights({
    includePredictions: true,
    refetchInterval: 5 * 60 * 1000, // Refresh every 5 minutes
  });

  const insights = data?.insights ?? [];
  const displayInsights = insights.slice(0, maxItems);
  const hasMore = insights.length > maxItems;

  // Group by severity for quick stats
  const severityCounts = insights.reduce(
    (acc, insight) => {
      const severity = insight.severity as InsightSeverity;
      acc[severity] = (acc[severity] || 0) + 1;
      return acc;
    },
    {} as Record<InsightSeverity, number>
  );

  const criticalCount = severityCounts[InsightSeverity.CRITICAL] || 0;
  const highCount = severityCounts[InsightSeverity.HIGH] || 0;

  const handleInsightClick = (insight: InsightResponse) => {
    if (insight.action_url) {
      navigate({ to: insight.action_url });
    }
  };

  return (
    <Card className={cn('flex flex-col', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-primary/10">
              <Lightbulb className="h-4 w-4 text-primary" />
            </div>
            <div>
              <CardTitle className="text-base">KI-Insights</CardTitle>
              <CardDescription className="text-xs">
                Proaktive Empfehlungen
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Severity Summary */}
            {criticalCount > 0 && (
              <Badge variant="destructive" className="text-xs">
                {criticalCount} kritisch
              </Badge>
            )}
            {highCount > 0 && (
              <Badge variant="outline" className="text-xs text-orange-500 border-orange-500">
                {highCount} hoch
              </Badge>
            )}

            {/* Refresh Button */}
            {showRefresh && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => refetch()}
                disabled={isFetching}
              >
                <RefreshCw
                  className={cn('h-4 w-4', isFetching && 'animate-spin')}
                />
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1 pt-0">
        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            <span className="text-sm">Lade Insights...</span>
          </div>
        ) : error ? (
          <div className="text-center py-8 text-muted-foreground">
            <AlertTriangle className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Insights konnten nicht geladen werden</p>
            <Button
              variant="ghost"
              size="sm"
              className="mt-2"
              onClick={() => refetch()}
            >
              Erneut versuchen
            </Button>
          </div>
        ) : insights.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Sparkles className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Keine Insights verfügbar</p>
            <p className="text-xs mt-1">Alles sieht gut aus!</p>
          </div>
        ) : (
          <ScrollArea className="h-[280px]">
            <div className="space-y-2">
              <AnimatePresence>
                {displayInsights.map((insight, index) => (
                  <InsightItem
                    key={insight.id}
                    insight={insight}
                    index={index}
                    onClick={() => handleInsightClick(insight)}
                  />
                ))}
              </AnimatePresence>
            </div>

            {/* Show More */}
            {hasMore && (
              <Button
                variant="ghost"
                className="w-full mt-3 text-xs"
                onClick={() => {
                  // Open AI assistant with insights tab
                  const event = new CustomEvent('open-ai-assistant', {
                    detail: { tab: 'insights' },
                  });
                  window.dispatchEvent(event);
                }}
              >
                Alle {insights.length} Insights anzeigen
                <ChevronRight className="ml-1 h-3 w-3" />
              </Button>
            )}
          </ScrollArea>
        )}

        {/* Last Updated */}
        {data?.generated_at && (
          <div className="mt-3 text-xs text-muted-foreground text-center">
            Aktualisiert:{' '}
            {new Date(data.generated_at).toLocaleTimeString('de-DE', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ===== Insight Item Component =====

interface InsightItemProps {
  insight: InsightResponse;
  index: number;
  onClick: () => void;
}

function InsightItem({ insight, index, onClick }: InsightItemProps) {
  const category = insight.category as InsightCategory;
  const severity = insight.severity as InsightSeverity;
  const CategoryIcon = CATEGORY_ICONS[category] || Lightbulb;
  const categoryMeta = CATEGORY_METADATA[category];
  const severityMeta = SEVERITY_METADATA[severity];

  return (
    <motion.button
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ delay: index * 0.05 }}
      onClick={onClick}
      className={cn(
        'w-full flex items-start gap-3 p-3 rounded-lg border text-left',
        'hover:bg-muted/50 transition-colors',
        'focus:outline-none focus:ring-2 focus:ring-primary/50'
      )}
    >
      {/* Icon */}
      <div className={cn('p-1.5 rounded-md flex-shrink-0', SEVERITY_COLORS[severity])}>
        <CategoryIcon className="h-3.5 w-3.5" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm truncate">{insight.title}</span>
          <Badge
            variant="outline"
            className={cn('text-[10px] flex-shrink-0', SEVERITY_COLORS[severity])}
          >
            {severityMeta?.label}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
          {insight.summary}
        </p>
        {categoryMeta && (
          <div className="flex items-center gap-1 mt-1">
            <Badge variant="secondary" className="text-[10px]">
              {categoryMeta.label}
            </Badge>
          </div>
        )}
      </div>

      {/* Arrow */}
      <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0 self-center" />
    </motion.button>
  );
}

export default InsightsWidget;
