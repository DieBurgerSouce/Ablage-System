/**
 * DocumentSummaryCard Component
 * Card showing AI-generated summary with key facts
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Sparkles, ChevronDown, ChevronUp, Calendar } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useSummary } from '../hooks/use-ki-pipeline-queries';

interface DocumentSummaryCardProps {
  documentId: string;
  className?: string;
}

export function DocumentSummaryCard({
  documentId,
  className,
}: DocumentSummaryCardProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const { data: summary, isLoading, error } = useSummary(documentId);

  if (isLoading) {
    return (
      <Card className={cn('w-full', className)}>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={cn('w-full', className)}>
        <CardContent className="py-8 text-center text-muted-foreground">
          Fehler beim Laden der Zusammenfassung
        </CardContent>
      </Card>
    );
  }

  if (!summary) {
    return (
      <Card className={cn('w-full', className)}>
        <CardContent className="py-8 text-center text-muted-foreground">
          Keine Zusammenfassung verfügbar
        </CardContent>
      </Card>
    );
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('de-DE', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(date);
  };

  const isLongSummary = summary.summary_text.length > 300;

  return (
    <Card className={cn('w-full', className)}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-purple-500" />
            KI-Zusammenfassung
          </CardTitle>
          <Badge variant="outline" className="text-xs">
            {summary.language.toUpperCase()}
          </Badge>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground mt-2">
          <Calendar className="h-3.5 w-3.5" />
          <span>{formatDate(summary.generated_at)}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-3">
          <p
            className={cn(
              'text-sm leading-relaxed',
              !isExpanded && isLongSummary && 'line-clamp-3'
            )}
          >
            {summary.summary_text}
          </p>
          {isLongSummary && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
              className="w-full"
            >
              {isExpanded ? (
                <>
                  <ChevronUp className="h-4 w-4 mr-1" />
                  Weniger anzeigen
                </>
              ) : (
                <>
                  <ChevronDown className="h-4 w-4 mr-1" />
                  Mehr anzeigen
                </>
              )}
            </Button>
          )}
        </div>

        {summary.key_facts.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold text-muted-foreground">
              Wichtige Punkte
            </h4>
            <ul className="space-y-2">
              {summary.key_facts.map((fact, index) => (
                <li key={index} className="flex items-start gap-2 text-sm">
                  <span className="text-primary mt-0.5">•</span>
                  <span className="flex-1">{fact}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
