/**
 * CorrectionQueue Component
 *
 * Zeigt niedrig-konfidente OCR-Extraktionen zur Korrektur.
 * Mit Prioritaets-Filter und Inline-Korrektur-Dialog.
 */

import { useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Info,
  ChevronDown,
  FileText,
  Building2,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { useCorrectionQueue, useClaimQueueItem } from '../hooks/use-ocr-feedback';
import type { QueueItem, QueuePriority } from '../api/ocr-feedback-api';
import { CorrectionDialog } from './CorrectionDialog';

interface CorrectionQueueProps {
  className?: string;
  onCorrectionComplete?: () => void;
}

const priorityConfig: Record<
  QueuePriority,
  { label: string; icon: React.ElementType; color: string; bgColor: string }
> = {
  critical: {
    label: 'Kritisch',
    icon: AlertCircle,
    color: 'text-red-500',
    bgColor: 'bg-red-500/10',
  },
  high: {
    label: 'Hoch',
    icon: AlertTriangle,
    color: 'text-orange-500',
    bgColor: 'bg-orange-500/10',
  },
  medium: {
    label: 'Mittel',
    icon: Info,
    color: 'text-yellow-500',
    bgColor: 'bg-yellow-500/10',
  },
  low: {
    label: 'Niedrig',
    icon: ChevronDown,
    color: 'text-blue-500',
    bgColor: 'bg-blue-500/10',
  },
};

function PriorityBadge({ priority }: { priority: QueuePriority }) {
  const config = priorityConfig[priority];
  const Icon = config.icon;

  return (
    <Badge className={cn('font-normal', config.bgColor, config.color, 'border-0')}>
      <Icon className="w-3 h-3 mr-1" />
      {config.label}
    </Badge>
  );
}

function ConfidenceMeter({ confidence }: { confidence: number }) {
  const percent = Math.round(confidence * 100);
  let color = 'bg-red-500';
  if (percent >= 55) color = 'bg-yellow-500';
  if (percent >= 65) color = 'bg-blue-500';

  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${percent}%` }} />
      </div>
      <span className="text-xs text-muted-foreground">{percent}%</span>
    </div>
  );
}

function QueueItemCard({
  item,
  onCorrect,
}: {
  item: QueueItem;
  onCorrect: (item: QueueItem) => void;
}) {
  return (
    <div className="border rounded-lg p-4 hover:bg-muted/50 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <PriorityBadge priority={item.priority} />
            <ConfidenceMeter confidence={item.confidence} />
          </div>

          <div className="flex items-center gap-2 text-sm mb-1">
            <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
            <span className="font-medium truncate">{item.document_filename}</span>
          </div>

          {item.entity_name && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
              <Building2 className="w-3 h-3 flex-shrink-0" />
              <span className="truncate">{item.entity_name}</span>
            </div>
          )}

          <div className="space-y-1">
            <div className="text-xs text-muted-foreground">
              Feld: <span className="font-medium">{item.field_name}</span>
              {item.document_type && (
                <span className="ml-2">
                  ({item.document_type})
                </span>
              )}
            </div>
            <div className="text-sm bg-muted p-2 rounded font-mono truncate">
              {item.ocr_value || <span className="text-muted-foreground italic">Leer</span>}
            </div>
            {item.suggested_value && (
              <div className="text-xs text-muted-foreground">
                Vorschlag: <span className="font-medium">{item.suggested_value}</span>
              </div>
            )}
          </div>
        </div>

        <Button variant="outline" size="sm" onClick={() => onCorrect(item)}>
          Korrigieren
        </Button>
      </div>
    </div>
  );
}

function QueueSkeleton() {
  return (
    <div className="space-y-3">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <Skeleton className="h-5 w-20" />
            <Skeleton className="h-1.5 w-16 rounded-full" />
          </div>
          <Skeleton className="h-4 w-48 mb-2" />
          <Skeleton className="h-3 w-32 mb-2" />
          <Skeleton className="h-8 w-full" />
        </div>
      ))}
    </div>
  );
}

export function CorrectionQueue({ className, onCorrectionComplete }: CorrectionQueueProps) {
  const [priorityFilter, setPriorityFilter] = useState<QueuePriority | 'all'>('all');
  const [selectedItem, setSelectedItem] = useState<QueueItem | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const { data, isLoading, error, refetch } = useCorrectionQueue({
    priority: priorityFilter === 'all' ? undefined : priorityFilter,
    limit: 10,
  });

  const handleCorrect = (item: QueueItem) => {
    setSelectedItem(item);
    setDialogOpen(true);
  };

  const handleCorrectionSuccess = () => {
    setDialogOpen(false);
    setSelectedItem(null);
    refetch();
    onCorrectionComplete?.();
  };

  return (
    <>
      <Card className={className}>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-orange-500" />
              Korrektur-Queue
              {data && (
                <Badge variant="secondary" className="ml-2">
                  {data.total}
                </Badge>
              )}
            </CardTitle>
            <Select
              value={priorityFilter}
              onValueChange={(v) => setPriorityFilter(v as QueuePriority | 'all')}
            >
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="Alle" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle</SelectItem>
                <SelectItem value="critical">Kritisch</SelectItem>
                <SelectItem value="high">Hoch</SelectItem>
                <SelectItem value="medium">Mittel</SelectItem>
                <SelectItem value="low">Niedrig</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <QueueSkeleton />
          ) : error ? (
            <div className="text-center py-8 text-muted-foreground">
              Queue konnte nicht geladen werden.
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <CheckCircle2 className="w-12 h-12 mx-auto mb-3 text-green-500 opacity-50" />
              <p className="font-medium">Keine Korrekturen erforderlich</p>
              <p className="text-sm mt-1">
                Alle OCR-Extraktionen haben ausreichende Konfidenz.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {data.items.map((item) => (
                <QueueItemCard key={item.id} item={item} onCorrect={handleCorrect} />
              ))}
              {data.total > data.items.length && (
                <div className="text-center pt-2">
                  <Button variant="ghost" size="sm">
                    {data.total - data.items.length} weitere anzeigen
                  </Button>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <CorrectionDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        item={selectedItem}
        onSuccess={handleCorrectionSuccess}
      />
    </>
  );
}
