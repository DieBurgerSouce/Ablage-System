/**
 * CrossDocumentMatchList Component
 * List of related documents in a chain (Bestellung → Lieferschein → Rechnung)
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Link2, FileText, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useCrossMatches } from '../hooks/use-ki-pipeline-queries';
import {
  DOCUMENT_TYPE_LABELS,
  MATCH_TYPE_LABELS,
  type CrossDocumentMatch,
} from '../types/ki-pipeline-types';

interface CrossDocumentMatchListProps {
  documentId: string;
  className?: string;
}

export function CrossDocumentMatchList({
  documentId,
  className,
}: CrossDocumentMatchListProps) {
  const { data: matches, isLoading, error } = useCrossMatches(documentId);

  if (isLoading) {
    return (
      <Card className={cn('w-full', className)}>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={cn('w-full', className)}>
        <CardContent className="py-8 text-center text-muted-foreground">
          Fehler beim Laden der Dokumentenverknüpfungen
        </CardContent>
      </Card>
    );
  }

  if (!matches || matches.length === 0) {
    return (
      <Card className={cn('w-full', className)}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Link2 className="h-5 w-5" />
            Dokumentenkette
          </CardTitle>
        </CardHeader>
        <CardContent className="py-8 text-center text-muted-foreground">
          Keine verknüpften Dokumente gefunden
        </CardContent>
      </Card>
    );
  }


  return (
    <Card className={cn('w-full', className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Link2 className="h-5 w-5" />
          Dokumentenkette
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {matches.map((match) => (
          <DocumentMatchItem key={match.document_id} match={match} />
        ))}
      </CardContent>
    </Card>
  );
}

interface DocumentMatchItemProps {
  match: CrossDocumentMatch;
}

function DocumentMatchItem({ match }: DocumentMatchItemProps) {
  const confidencePercent = Math.round(match.confidence * 100);
  const typeLabel = DOCUMENT_TYPE_LABELS[match.document_type] || match.document_type;
  const matchTypeLabel = MATCH_TYPE_LABELS[match.match_type] || match.match_type;

  const getConfidenceBadgeClass = () => {
    if (match.confidence >= 0.9) return 'bg-green-500 text-white';
    if (match.confidence >= 0.6) return 'bg-yellow-500 text-white';
    return 'bg-red-500 text-white';
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('de-DE', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(date);
  };

  return (
    <div className="flex items-center gap-3 p-4 border rounded-lg hover:bg-accent transition-colors cursor-pointer">
      <div className="flex-shrink-0">
        <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
          <FileText className="h-5 w-5 text-primary" />
        </div>
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium truncate">{typeLabel}</span>
          <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          <Badge variant="outline" className="text-xs">
            {matchTypeLabel}
          </Badge>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>ID: {match.document_id.substring(0, 8)}...</span>
          <span>{formatDate(match.created_at)}</span>
          {match.matched_fields.length > 0 && (
            <span>{match.matched_fields.length} Felder</span>
          )}
        </div>
      </div>

      <div className="flex-shrink-0">
        <Badge className={cn('font-semibold', getConfidenceBadgeClass())}>
          {confidencePercent}%
        </Badge>
      </div>
    </div>
  );
}
