/**
 * AnnotationSidebar - Seitenleiste fuer Dokument-Annotationen
 *
 * Zeigt alle Annotationen gruppiert nach Seite mit Filter-Optionen.
 * Unterstuetzt Status- und Typ-Filter sowie Seiten-Gruppierung.
 */

import { useState, useMemo } from 'react';
import {
  MessageSquare,
  CheckCircle,
  Circle,
  ChevronDown,
  ChevronRight,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { useAnnotations, useResolveAnnotation } from '../hooks/use-annotations';
import type { Annotation, AnnotationType } from '../api/annotations-api';

interface AnnotationSidebarProps {
  documentId: string;
  onAnnotationClick?: (annotation: Annotation) => void;
  className?: string;
}

const typeLabels: Record<AnnotationType, string> = {
  comment: 'Kommentar',
  highlight: 'Markierung',
  drawing: 'Zeichnung',
  approval: 'Genehmigung',
  rejection: 'Ablehnung',
};

export function AnnotationSidebar({
  documentId,
  onAnnotationClick,
  className,
}: AnnotationSidebarProps) {
  const { data: annotations, isLoading, isError } = useAnnotations(documentId);
  const resolveMutation = useResolveAnnotation(documentId);

  const [statusFilter, setStatusFilter] = useState<'all' | 'open' | 'resolved'>('all');
  const [typeFilter, setTypeFilter] = useState<AnnotationType | 'all'>('all');
  const [expandedPages, setExpandedPages] = useState<Set<number>>(new Set());

  // Filtern und nach Seite gruppieren
  const groupedAnnotations = useMemo(() => {
    if (!annotations) return new Map<number, Annotation[]>();

    let filtered = annotations;

    if (statusFilter === 'open') {
      filtered = filtered.filter((a) => !a.is_resolved);
    } else if (statusFilter === 'resolved') {
      filtered = filtered.filter((a) => a.is_resolved);
    }

    if (typeFilter !== 'all') {
      filtered = filtered.filter((a) => a.annotation_type === typeFilter);
    }

    const grouped = new Map<number, Annotation[]>();
    for (const a of filtered) {
      const pageAnnotations = grouped.get(a.page) || [];
      grouped.set(a.page, [...pageAnnotations, a]);
    }

    // Seiten sortieren
    return new Map([...grouped.entries()].sort(([a], [b]) => a - b));
  }, [annotations, statusFilter, typeFilter]);

  const togglePage = (page: number) => {
    setExpandedPages((prev) => {
      const next = new Set(prev);
      if (next.has(page)) {
        next.delete(page);
      } else {
        next.add(page);
      }
      return next;
    });
  };

  const totalCount = annotations?.length ?? 0;
  const openCount = annotations?.filter((a) => !a.is_resolved).length ?? 0;

  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Lade Annotationen...
          </div>
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-2 text-destructive">
            <AlertCircle className="h-4 w-4" />
            Fehler beim Laden der Annotationen
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-base">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4" />
            Annotationen
            <Badge variant="secondary" className="text-xs">
              {openCount} offen / {totalCount} gesamt
            </Badge>
          </div>
        </CardTitle>

        {/* Filter */}
        <div className="flex gap-2 pt-2">
          <Select
            value={statusFilter}
            onValueChange={(v) => setStatusFilter(v as typeof statusFilter)}
          >
            <SelectTrigger className="h-8 text-xs w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle</SelectItem>
              <SelectItem value="open">Offen</SelectItem>
              <SelectItem value="resolved">Erledigt</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={typeFilter}
            onValueChange={(v) => setTypeFilter(v as typeof typeFilter)}
          >
            <SelectTrigger className="h-8 text-xs w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Typen</SelectItem>
              <SelectItem value="comment">Kommentar</SelectItem>
              <SelectItem value="highlight">Markierung</SelectItem>
              <SelectItem value="approval">Genehmigung</SelectItem>
              <SelectItem value="rejection">Ablehnung</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        <ScrollArea className="h-[400px]">
          {groupedAnnotations.size === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm px-6">
              <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" />
              Keine Annotationen vorhanden.
            </div>
          ) : (
            <div className="divide-y">
              {[...groupedAnnotations.entries()].map(([page, pageAnnotations]) => (
                <div key={page}>
                  {/* Seiten-Header */}
                  <button
                    className="w-full flex items-center justify-between px-4 py-2 text-sm font-medium hover:bg-muted/50 transition-colors"
                    onClick={() => togglePage(page)}
                  >
                    <span>Seite {page}</span>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">
                        {pageAnnotations.length}
                      </Badge>
                      {expandedPages.has(page) ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </div>
                  </button>

                  {/* Annotationen der Seite */}
                  {expandedPages.has(page) && (
                    <div className="px-4 pb-2 space-y-2">
                      {pageAnnotations.map((annotation) => (
                        <div
                          key={annotation.id}
                          className={cn(
                            'p-2 rounded-md border cursor-pointer hover:bg-muted/50 transition-colors text-sm',
                            annotation.is_resolved && 'opacity-60'
                          )}
                          onClick={() => onAnnotationClick?.(annotation)}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <div className="flex items-center gap-1.5">
                              {annotation.is_resolved ? (
                                <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                              ) : (
                                <Circle className="h-3.5 w-3.5 text-muted-foreground" />
                              )}
                              <Badge variant="secondary" className="text-[10px] px-1 py-0">
                                {typeLabels[annotation.annotation_type]}
                              </Badge>
                            </div>
                            {!annotation.is_resolved && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 text-xs px-2"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  resolveMutation.mutate(annotation.id);
                                }}
                                disabled={resolveMutation.isPending}
                              >
                                Erledigen
                              </Button>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground line-clamp-2">
                            {annotation.content}
                          </p>
                          <p className="text-[10px] text-muted-foreground mt-1">
                            {annotation.user_name || 'Unbekannt'} &middot;{' '}
                            {new Date(annotation.created_at).toLocaleDateString('de-DE')}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
