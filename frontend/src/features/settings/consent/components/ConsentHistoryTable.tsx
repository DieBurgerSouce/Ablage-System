/**
 * ConsentHistoryTable Component
 *
 * Zeigt die vollständige Historie aller Einwilligungs-Änderungen.
 */

import {
  CheckCircle2,
  XCircle,
  ArrowRight,
  History,
  Filter,
} from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import type { ConsentHistoryEntry, ConsentScope } from '../types';
import { CONSENT_SCOPE_LABELS, ConsentScope as ConsentScopeEnum } from '../types';

interface ConsentHistoryTableProps {
  history: ConsentHistoryEntry[];
  isLoading?: boolean;
  selectedScope?: ConsentScope;
  onScopeChange?: (scope: ConsentScope | undefined) => void;
}

export function ConsentHistoryTable({
  history,
  isLoading = false,
  selectedScope,
  onScopeChange,
}: ConsentHistoryTableProps) {
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getActionLabel = (action: string) => {
    switch (action) {
      case 'grant':
      case 'granted':
        return 'Erteilt';
      case 'withdraw':
      case 'withdrawn':
        return 'Widerrufen';
      case 'update':
      case 'updated':
        return 'Aktualisiert';
      default:
        return action;
    }
  };

  const getActionBadgeVariant = (action: string): 'default' | 'outline' | 'destructive' | 'secondary' => {
    switch (action) {
      case 'grant':
      case 'granted':
        return 'default';
      case 'withdraw':
      case 'withdrawn':
        return 'destructive';
      default:
        return 'secondary';
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Filter */}
      {onScopeChange && (
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <Select
            value={selectedScope || 'all'}
            onValueChange={(value) =>
              onScopeChange(value === 'all' ? undefined : (value as ConsentScope))
            }
          >
            <SelectTrigger className="w-[240px]">
              <SelectValue placeholder="Alle Bereiche" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Bereiche</SelectItem>
              {Object.values(ConsentScopeEnum).map((scope) => (
                <SelectItem key={scope} value={scope}>
                  {CONSENT_SCOPE_LABELS[scope]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {history.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          <History className="h-12 w-12 mx-auto mb-3 opacity-50" />
          <p>Keine Einträge gefunden</p>
          <p className="text-sm">
            Hier werden alle Änderungen an Ihren Einwilligungen angezeigt.
          </p>
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Datum</TableHead>
                <TableHead>Bereich</TableHead>
                <TableHead>Aktion</TableHead>
                <TableHead>Änderung</TableHead>
                <TableHead className="hidden md:table-cell">Grund</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="font-mono text-sm">
                    {formatDate(entry.created_at)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {CONSENT_SCOPE_LABELS[entry.scope as ConsentScope] || entry.scope}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={getActionBadgeVariant(entry.action)}>
                      {getActionLabel(entry.action)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2 text-sm">
                      <span
                        className={cn(
                          'flex items-center gap-1',
                          entry.previous_value === true
                            ? 'text-green-600'
                            : entry.previous_value === false
                            ? 'text-red-600'
                            : 'text-muted-foreground'
                        )}
                      >
                        {entry.previous_value === true ? (
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        ) : entry.previous_value === false ? (
                          <XCircle className="h-3.5 w-3.5" />
                        ) : (
                          <span className="text-xs">-</span>
                        )}
                      </span>
                      <ArrowRight className="h-3 w-3 text-muted-foreground" />
                      <span
                        className={cn(
                          'flex items-center gap-1',
                          entry.new_value ? 'text-green-600' : 'text-red-600'
                        )}
                      >
                        {entry.new_value ? (
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        ) : (
                          <XCircle className="h-3.5 w-3.5" />
                        )}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="hidden md:table-cell text-sm text-muted-foreground max-w-[200px] truncate">
                    {entry.reason || '-'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
