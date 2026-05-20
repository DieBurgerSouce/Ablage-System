// Context Sidebar - Shows context-specific hints for current entity

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertCircle, Lightbulb } from 'lucide-react';
import { HintCard } from './HintCard';
import { useContextHintsQuery } from '../hooks/use-proactive-assistant-queries';
import { UI_LABELS } from '../types/proactive-assistant-types';

interface ContextSidebarProps {
  entityType: string;
  entityId: string;
  className?: string;
}

export function ContextSidebar({
  entityType,
  entityId,
  className = '',
}: ContextSidebarProps) {
  const { data: hints, isLoading, error } = useContextHintsQuery(
    entityType,
    entityId
  );

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Lightbulb className="h-4 w-4 text-yellow-500" />
          <span>Kontextbezogene Hinweise</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Error State */}
        {error && (
          <div className="flex items-start gap-2 text-destructive">
            <AlertCircle className="h-5 w-5 mt-0.5" />
            <p className="text-sm">{UI_LABELS.messages.errorLoadingHints}</p>
          </div>
        )}

        {/* Loading State */}
        {isLoading && (
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && hints && hints.length === 0 && (
          <div className="text-center py-8">
            <p className="text-sm text-muted-foreground">
              {UI_LABELS.messages.noContextHints}
            </p>
          </div>
        )}

        {/* Hints List */}
        {!isLoading && !error && hints && hints.length > 0 && (
          <div className="space-y-3">
            {hints.map((hint) => (
              <HintCard key={hint.hintId} hint={hint} compact />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
