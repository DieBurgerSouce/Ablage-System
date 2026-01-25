/**
 * Low Confidence Queue Component
 * Zeigt Dokumente mit niedriger OCR-Confidence zur Korrektur
 */

import { useState } from 'react';
import { FileText, AlertTriangle, ChevronRight, Filter } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { useLowConfidenceQueue, useAvailableBackends } from '../hooks';
import type { LowConfidenceDocument, QueueFilters } from '../types';

interface LowConfidenceQueueProps {
  onSelectDocument: (doc: LowConfidenceDocument) => void;
  selectedDocumentId?: string;
}

const DOCUMENT_TYPES = [
  { value: 'all', label: 'Alle Typen' },
  { value: 'invoice', label: 'Rechnung' },
  { value: 'receipt', label: 'Beleg' },
  { value: 'contract', label: 'Vertrag' },
  { value: 'letter', label: 'Brief' },
  { value: 'other', label: 'Sonstige' },
];

function getConfidenceBadgeVariant(confidence: number): 'destructive' | 'secondary' | 'default' {
  if (confidence < 0.5) return 'destructive';
  if (confidence < 0.7) return 'secondary';
  return 'default';
}

function formatConfidence(confidence: number): string {
  return `${(confidence * 100).toFixed(0)}%`;
}

export function LowConfidenceQueue({
  onSelectDocument,
  selectedDocumentId,
}: LowConfidenceQueueProps) {
  const [filters, setFilters] = useState<QueueFilters>({
    maxConfidence: 0.8,
    backend: null,
    documentType: null,
    hasUmlauts: null,
  });
  const [showFilters, setShowFilters] = useState(false);

  const { data, isLoading, error } = useLowConfidenceQueue(filters, 50, 0);
  const { data: backends = [] } = useAvailableBackends();

  const handleBackendChange = (value: string) => {
    setFilters((prev) => ({
      ...prev,
      backend: value === 'all' ? null : value,
    }));
  };

  const handleDocTypeChange = (value: string) => {
    setFilters((prev) => ({
      ...prev,
      documentType: value === 'all' ? null : value,
    }));
  };

  const handleConfidenceChange = (value: number[]) => {
    setFilters((prev) => ({
      ...prev,
      maxConfidence: value[0],
    }));
  };

  if (error) {
    return (
      <Card className="h-full">
        <CardHeader>
          <CardTitle className="text-sm font-medium text-destructive">
            Fehler beim Laden der Queue
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Die Dokumente konnten nicht geladen werden.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex-shrink-0 pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">
            Korrektur-Queue
            {data && (
              <Badge variant="secondary" className="ml-2">
                {data.total}
              </Badge>
            )}
          </CardTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowFilters(!showFilters)}
          >
            <Filter className="h-4 w-4" />
          </Button>
        </div>

        {showFilters && (
          <div className="mt-4 space-y-4 pt-4 border-t">
            <div className="space-y-2">
              <Label className="text-xs">Max. Confidence: {formatConfidence(filters.maxConfidence)}</Label>
              <Slider
                value={[filters.maxConfidence]}
                onValueChange={handleConfidenceChange}
                min={0.1}
                max={1}
                step={0.05}
                className="w-full"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Backend</Label>
                <Select
                  value={filters.backend || 'all'}
                  onValueChange={handleBackendChange}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Alle Backends</SelectItem>
                    {backends.map((backend) => (
                      <SelectItem key={backend} value={backend}>
                        {backend}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Dokumenttyp</Label>
                <Select
                  value={filters.documentType || 'all'}
                  onValueChange={handleDocTypeChange}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DOCUMENT_TYPES.map((type) => (
                      <SelectItem key={type.value} value={type.value}>
                        {type.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        )}
      </CardHeader>

      <CardContent className="flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="flex items-center gap-3 p-3 border rounded-lg">
                  <Skeleton className="h-10 w-10 rounded" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-3 w-1/2" />
                  </div>
                </div>
              ))}
            </div>
          ) : data?.documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full p-8 text-center">
              <AlertTriangle className="h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-sm text-muted-foreground">
                Keine Dokumente mit niedriger Confidence gefunden.
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Erhoehen Sie den Max-Confidence-Filter.
              </p>
            </div>
          ) : (
            <div className="space-y-1 p-2">
              {data?.documents.map((doc) => (
                <button
                  key={doc.id}
                  onClick={() => onSelectDocument(doc)}
                  className={`w-full flex items-center gap-3 p-3 rounded-lg text-left transition-colors hover:bg-accent ${
                    selectedDocumentId === doc.id ? 'bg-accent' : ''
                  }`}
                >
                  <div className="flex-shrink-0 h-10 w-10 rounded bg-muted flex items-center justify-center">
                    <FileText className="h-5 w-5 text-muted-foreground" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {doc.filename}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge
                        variant={getConfidenceBadgeVariant(doc.overallConfidence)}
                        className="text-xs"
                      >
                        {formatConfidence(doc.overallConfidence)}
                      </Badge>
                      <span className="text-xs text-muted-foreground truncate">
                        {doc.backendUsed}
                      </span>
                    </div>
                  </div>

                  <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                </button>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
