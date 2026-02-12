/**
 * Queue Items Table
 *
 * Tabelle mit Warteschlangen-Items und Prioritäts-Anzeige.
 */

import { useState } from 'react';
import {
  FileText,
  Clock,
  Banknote,
  AlertTriangle,
  ChevronUp,
  ChevronDown,
  MoreHorizontal,
  Pause,
  Play,
  Eye,
  Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { Link } from '@tanstack/react-router';
import {
  useQueueItems,
  useChangePriority,
  usePauseResumeItem,
  type QueueItem,
  type QueueStatus,
  type PriorityReason,
} from '../hooks/useSmartQueue';

const STATUS_CONFIG: Record<QueueStatus, { label: string; color: string }> = {
  waiting: { label: 'Wartend', color: 'text-yellow-500' },
  processing: { label: 'Wird verarbeitet', color: 'text-blue-500' },
  completed: { label: 'Abgeschlossen', color: 'text-green-500' },
  failed: { label: 'Fehlgeschlagen', color: 'text-red-500' },
  paused: { label: 'Pausiert', color: 'text-gray-500' },
};

const PRIORITY_REASON_LABELS: Record<PriorityReason, { label: string; icon: typeof Banknote }> = {
  skonto_deadline: { label: 'Skonto-Frist', icon: Banknote },
  dunning_notice: { label: 'Mahnung', icon: AlertTriangle },
  manual_high: { label: 'Manuell erhöht', icon: ChevronUp },
  urgent_flag: { label: 'Dringend', icon: AlertTriangle },
  vip_customer: { label: 'VIP-Kunde', icon: FileText },
  high_amount: { label: 'Hoher Betrag', icon: Banknote },
  default: { label: 'Standard', icon: FileText },
};

function PriorityBadge({ priority }: { priority: number }) {
  let variant: 'destructive' | 'default' | 'secondary' | 'outline' = 'outline';
  let label = 'Normal';

  if (priority >= 9) {
    variant = 'destructive';
    label = 'Kritisch';
  } else if (priority >= 7) {
    variant = 'default';
    label = 'Hoch';
  } else if (priority >= 4) {
    variant = 'secondary';
    label = 'Normal';
  } else {
    variant = 'outline';
    label = 'Niedrig';
  }

  return (
    <Badge variant={variant} className="gap-1">
      {label} ({priority})
    </Badge>
  );
}

function formatWaitTime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
}

function QueueItemRow({ item }: { item: QueueItem }) {
  const changePriority = useChangePriority();
  const pauseResume = usePauseResumeItem();

  const handlePriorityChange = async (newPriority: number) => {
    try {
      await changePriority.mutateAsync({
        documentId: item.document_id,
        priority: newPriority,
        reason: 'manual',
      });
      toast.success('Priorität geändert');
    } catch {
      toast.error('Fehler beim Ändern der Priorität');
    }
  };

  const handlePauseResume = async () => {
    const action = item.status === 'paused' ? 'resume' : 'pause';
    try {
      await pauseResume.mutateAsync({ documentId: item.document_id, action });
      toast.success(action === 'pause' ? 'Pausiert' : 'Fortgesetzt');
    } catch {
      toast.error('Fehler bei der Aktion');
    }
  };

  const statusConfig = STATUS_CONFIG[item.status];

  return (
    <TableRow>
      <TableCell>
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <div>
            <Link
              to="/ablage/$category/$entityId/$folderId/$documentId"
              params={{
                category: 'kunden',
                entityId: 'unknown',
                folderId: 'unknown',
                documentId: item.document_id,
              }}
              className="font-medium hover:underline"
            >
              {item.document_name}
            </Link>
            {item.document_type && (
              <p className="text-xs text-muted-foreground">{item.document_type}</p>
            )}
          </div>
        </div>
      </TableCell>

      <TableCell>
        <div className="space-y-1">
          <PriorityBadge priority={item.priority} />
          <div className="flex flex-wrap gap-1">
            {item.priority_reasons
              .filter((r) => r !== 'default')
              .map((reason) => {
                const config = PRIORITY_REASON_LABELS[reason];
                const Icon = config.icon;
                return (
                  <Badge key={reason} variant="outline" className="text-xs gap-1">
                    <Icon className="h-3 w-3" />
                    {config.label}
                  </Badge>
                );
              })}
          </div>
        </div>
      </TableCell>

      <TableCell>
        <div className="flex items-center gap-2">
          {item.status === 'processing' && (
            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
          )}
          <span className={statusConfig.color}>{statusConfig.label}</span>
        </div>
        {item.backend && (
          <p className="text-xs text-muted-foreground">{item.backend}</p>
        )}
      </TableCell>

      <TableCell>
        <div className="flex items-center gap-1 text-sm text-muted-foreground">
          <Clock className="h-3 w-3" />
          {formatWaitTime(item.wait_time_seconds)}
        </div>
      </TableCell>

      <TableCell>
        {item.skonto_deadline && (
          <Badge variant="outline" className="text-amber-500 border-amber-500 text-xs">
            <Banknote className="h-3 w-3 mr-1" />
            {new Date(item.skonto_deadline).toLocaleDateString('de-DE')}
          </Badge>
        )}
        {item.is_dunning && (
          <Badge variant="outline" className="text-red-500 border-red-500 text-xs">
            <AlertTriangle className="h-3 w-3 mr-1" />
            Mahnung
          </Badge>
        )}
        {item.detected_amount && (
          <p className="text-xs text-muted-foreground mt-1">
            {item.detected_amount.toLocaleString('de-DE', {
              style: 'currency',
              currency: 'EUR',
            })}
          </p>
        )}
      </TableCell>

      <TableCell>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => handlePriorityChange(10)}>
              <ChevronUp className="h-4 w-4 mr-2 text-red-500" />
              Höchste Priorität (10)
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => handlePriorityChange(7)}>
              <ChevronUp className="h-4 w-4 mr-2 text-orange-500" />
              Hohe Priorität (7)
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => handlePriorityChange(5)}>
              Normal (5)
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => handlePriorityChange(2)}>
              <ChevronDown className="h-4 w-4 mr-2 text-gray-500" />
              Niedrige Priorität (2)
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {(item.status === 'waiting' || item.status === 'paused') && (
              <DropdownMenuItem onClick={handlePauseResume}>
                {item.status === 'paused' ? (
                  <>
                    <Play className="h-4 w-4 mr-2" />
                    Fortsetzen
                  </>
                ) : (
                  <>
                    <Pause className="h-4 w-4 mr-2" />
                    Pausieren
                  </>
                )}
              </DropdownMenuItem>
            )}
            <DropdownMenuItem asChild>
              <Link
                to="/ablage/$category/$entityId/$folderId/$documentId"
                params={{
                  category: 'kunden',
                  entityId: 'unknown',
                  folderId: 'unknown',
                  documentId: item.document_id,
                }}
              >
                <Eye className="h-4 w-4 mr-2" />
                Dokument anzeigen
              </Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </TableCell>
    </TableRow>
  );
}

export function QueueItemsTable() {
  const [statusFilter, setStatusFilter] = useState<QueueStatus | 'all'>('all');

  const { data, isLoading } = useQueueItems(
    statusFilter === 'all' ? undefined : statusFilter,
    100
  );

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Warteschlange
          </CardTitle>
          <CardDescription>
            Dokumente sortiert nach Priorität
          </CardDescription>
        </div>
        <Select
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v as QueueStatus | 'all')}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Alle Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Status</SelectItem>
            <SelectItem value="waiting">Wartend</SelectItem>
            <SelectItem value="processing">In Bearbeitung</SelectItem>
            <SelectItem value="paused">Pausiert</SelectItem>
            <SelectItem value="completed">Abgeschlossen</SelectItem>
            <SelectItem value="failed">Fehlgeschlagen</SelectItem>
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : data?.items && data.items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Dokument</TableHead>
                <TableHead>Priorität</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Wartezeit</TableHead>
                <TableHead>Details</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((item) => (
                <QueueItemRow key={item.id} item={item} />
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <Clock className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>Keine Dokumente in der Warteschlange</p>
          </div>
        )}

        {data && data.total > data.items.length && (
          <p className="text-sm text-muted-foreground mt-4 text-center">
            Zeige {data.items.length} von {data.total} Dokumenten
          </p>
        )}
      </CardContent>
    </Card>
  );
}
