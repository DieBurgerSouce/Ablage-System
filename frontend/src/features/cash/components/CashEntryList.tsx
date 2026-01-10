/**
 * Cash Entry List
 *
 * Liste der Kassenbucheintraege mit Filterung und Paginierung.
 */

import * as React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Plus,
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  XCircle,
  Utensils,
} from 'lucide-react';
import { useEntries } from '../hooks/use-cash-queries';
import { formatCurrency, formatDate, formatEntryType, getEntryTypeColor } from '../utils/format';
import type { CashEntry, CashEntryType } from '@/types/models/cash';
import { cn } from '@/lib/utils';

interface CashEntryListProps {
  registerId: string;
  onCreateEntry?: () => void;
  onCancelEntry?: (entry: CashEntry) => void;
  onViewEntry?: (entry: CashEntry) => void;
  className?: string;
}

const ENTRY_TYPE_OPTIONS: { value: CashEntryType | 'all'; label: string }[] = [
  { value: 'all', label: 'Alle Typen' },
  { value: 'income', label: 'Einnahme' },
  { value: 'expense', label: 'Ausgabe' },
  { value: 'deposit', label: 'Einlage' },
  { value: 'withdrawal', label: 'Entnahme' },
  { value: 'entertainment', label: 'Bewirtung' },
  { value: 'travel', label: 'Reisekosten' },
  { value: 'cancellation', label: 'Storno' },
];

const PAGE_SIZE = 20;

export function CashEntryList({
  registerId,
  onCreateEntry,
  onCancelEntry,
  onViewEntry,
  className,
}: CashEntryListProps) {
  const [page, setPage] = React.useState(0);
  const [typeFilter, setTypeFilter] = React.useState<CashEntryType | 'all'>('all');
  const [startDate, setStartDate] = React.useState<string>('');
  const [endDate, setEndDate] = React.useState<string>('');

  const { data: response, isLoading, error } = useEntries({
    register_id: registerId,
    entry_type: typeFilter === 'all' ? undefined : typeFilter,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  });

  const entries = response?.entries ?? [];
  const totalCount = response?.total ?? 0;
  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  const handlePrevPage = () => setPage((p) => Math.max(0, p - 1));
  const handleNextPage = () => setPage((p) => Math.min(totalPages - 1, p + 1));

  // Reset page when filter changes
  React.useEffect(() => {
    setPage(0);
  }, [typeFilter, startDate, endDate]);

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Kassenbuch</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Eintraege
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Kassenbuch</CardTitle>
            <CardDescription>
              {totalCount} {totalCount === 1 ? 'Eintrag' : 'Einträge'}
            </CardDescription>
          </div>
          {onCreateEntry && (
            <Button onClick={onCreateEntry}>
              <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
              Neuer Eintrag
            </Button>
          )}
        </div>

        {/* Filter */}
        <div className="flex flex-wrap gap-2 pt-4">
          <Select
            value={typeFilter}
            onValueChange={(v) => setTypeFilter(v as CashEntryType | 'all')}
          >
            <SelectTrigger className="w-[150px]">
              <Filter className="mr-2 h-4 w-4" aria-hidden="true" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ENTRY_TYPE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Input
            type="date"
            placeholder="Von"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-[150px]"
          />

          <Input
            type="date"
            placeholder="Bis"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-[150px]"
          />

          {(typeFilter !== 'all' || startDate || endDate) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setTypeFilter('all');
                setStartDate('');
                setEndDate('');
              }}
            >
              Filter zurücksetzen
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : entries.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Keine Eintraege gefunden.
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[60px]">Nr.</TableHead>
                  <TableHead>Datum</TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead>Beschreibung</TableHead>
                  <TableHead className="text-right">Betrag</TableHead>
                  <TableHead className="text-right">Saldo</TableHead>
                  <TableHead className="w-[80px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entries.map((entry) => (
                  <CashEntryRow
                    key={entry.id}
                    entry={entry}
                    onCancel={onCancelEntry}
                    onView={onViewEntry}
                  />
                ))}
              </TableBody>
            </Table>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-4">
                <div className="text-sm text-muted-foreground">
                  Seite {page + 1} von {totalPages}
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handlePrevPage}
                    disabled={page === 0}
                  >
                    <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                    Zurück
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleNextPage}
                    disabled={page >= totalPages - 1}
                  >
                    Weiter
                    <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

interface CashEntryRowProps {
  entry: CashEntry;
  onCancel?: (entry: CashEntry) => void;
  onView?: (entry: CashEntry) => void;
}

function CashEntryRow({ entry, onCancel, onView }: CashEntryRowProps) {
  const color = getEntryTypeColor(entry.entry_type);
  const isIncome = ['income', 'deposit', 'difference_plus', 'opening'].includes(entry.entry_type);
  const isCancelled = entry.is_cancelled;
  const isCancellation = entry.entry_type === 'cancellation';
  const isEntertainment = entry.entry_type === 'entertainment';

  return (
    <TableRow
      className={cn(
        isCancelled && 'opacity-50 line-through',
        onView && 'cursor-pointer hover:bg-muted/50'
      )}
      onClick={() => onView?.(entry)}
    >
      <TableCell className="font-mono text-xs">{entry.entry_number}</TableCell>
      <TableCell>{formatDate(entry.entry_date)}</TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Badge
            variant={
              color === 'green' ? 'default' :
              color === 'red' ? 'destructive' :
              color === 'yellow' ? 'secondary' :
              'outline'
            }
          >
            {formatEntryType(entry.entry_type)}
          </Badge>
          {isEntertainment && entry.entertainment_data && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span role="img" aria-label="Bewirtungskosten">
                    <Utensils className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{entry.entertainment_data.guests?.length || 0} Gaeste</p>
                  <p>{entry.entertainment_data.business_reason}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
          {isCancelled && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span role="img" aria-label="Buchung wurde storniert">
                    <XCircle className="h-3 w-3 text-destructive" aria-hidden="true" />
                  </span>
                </TooltipTrigger>
                <TooltipContent>Storniert</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
      </TableCell>
      <TableCell className="max-w-[200px] truncate">
        {entry.description}
        {isCancellation && entry.cancellation_reason && (
          <span className="text-xs text-muted-foreground ml-1">
            ({entry.cancellation_reason})
          </span>
        )}
      </TableCell>
      <TableCell className="text-right font-mono">
        <span className={isIncome ? 'text-green-600' : 'text-red-600'}>
          {isIncome ? '+' : '-'}{formatCurrency(Math.abs(entry.amount))}
        </span>
      </TableCell>
      <TableCell className="text-right font-mono">
        {formatCurrency(entry.balance_after)}
      </TableCell>
      <TableCell>
        {onCancel && !isCancelled && !isCancellation && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={(e) => {
              e.stopPropagation();
              onCancel(entry);
            }}
          >
            <AlertCircle className="h-4 w-4 text-destructive" aria-hidden="true" />
            <span className="sr-only">Stornieren</span>
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

export default CashEntryList;
