/**
 * MissedSkontoDashboard - Verpasste Skonto-Möglichkeiten Dashboard
 *
 * Zeigt alle verpassten Skonto-Fristen mit:
 * - Statistik-Cards (Gesamt verpasst, Anzahl, etc.)
 * - Filter nach Zeitraum
 * - Sortierbare Tabelle
 * - Export-Funktion (Excel/CSV)
 * - Pagination
 */

import { useState, useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import {
  TrendingDown,
  Calendar,
  FileDown,
  AlertTriangle,
  DollarSign,
  FileText,
  ExternalLink,
  Loader2,
} from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { useMissedSkonto, useExportMissedSkonto } from './hooks';
import type { MissedSkontoFilter } from './types';

const DEFAULT_PER_PAGE = 20;

export function MissedSkontoDashboard() {
  const exportMutation = useExportMissedSkonto();

  // Filter State
  const [filter, setFilter] = useState<MissedSkontoFilter>({
    page: 1,
    perPage: DEFAULT_PER_PAGE,
  });

  // Date Range State (letzten 12 Monate als Default)
  const [startDate, setStartDate] = useState<string>(() => {
    const date = new Date();
    date.setMonth(date.getMonth() - 12);
    return date.toISOString().split('T')[0];
  });
  const [endDate, setEndDate] = useState<string>(() => {
    return new Date().toISOString().split('T')[0];
  });

  // Query
  const { data, isLoading, isError } = useMissedSkonto({
    ...filter,
    startDate,
    endDate,
  });

  // Handler: Zeitraum ändern
  const handleDateChange = (type: 'start' | 'end', value: string) => {
    if (type === 'start') {
      setStartDate(value);
    } else {
      setEndDate(value);
    }
    setFilter((prev) => ({ ...prev, page: 1 })); // Reset to page 1
  };

  // Handler: Export
  const handleExport = async (format: 'xlsx' | 'csv') => {
    await exportMutation.mutateAsync({
      format,
      filter: { startDate, endDate },
    });
  };

  // Handler: Pagination
  const handlePageChange = (newPage: number) => {
    setFilter((prev) => ({ ...prev, page: newPage }));
  };

  // Berechne Statistiken
  const stats = useMemo(() => {
    if (!data) return null;
    return {
      totalMissed: data.total,
      totalAmount: data.totalMissedAmount,
      averageAmount: data.total > 0 ? data.totalMissedAmount / data.total : 0,
    };
  }, [data]);

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <TrendingDown className="w-8 h-8 text-red-600" />
          Verpasste Skonto-Möglichkeiten
        </h1>
        <p className="text-muted-foreground mt-2">
          Übersicht über nicht genutzte Skonto-Fristen und verpasste Ersparnisse
        </p>
      </div>

      {/* Stats Cards */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-3">
                <Skeleton className="h-4 w-24" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-32" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : stats ? (
        <div className="grid gap-4 md:grid-cols-3">
          <StatsCard
            title="Verpasste Rechnungen"
            value={stats.totalMissed.toString()}
            icon={FileText}
            color="blue"
          />
          <StatsCard
            title="Verpasste Ersparnis"
            value={new Intl.NumberFormat('de-DE', {
              style: 'currency',
              currency: 'EUR',
            }).format(stats.totalAmount)}
            icon={DollarSign}
            color="red"
          />
          <StatsCard
            title="Ø Skonto-Betrag"
            value={new Intl.NumberFormat('de-DE', {
              style: 'currency',
              currency: 'EUR',
            }).format(stats.averageAmount)}
            icon={TrendingDown}
            color="yellow"
          />
        </div>
      ) : null}

      {/* Filter & Export */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Filter & Export</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-4">
            {/* Start Date */}
            <div className="space-y-2 flex-1 min-w-[200px]">
              <Label htmlFor="start-date">Von</Label>
              <Input
                id="start-date"
                type="date"
                value={startDate}
                onChange={(e) => handleDateChange('start', e.target.value)}
              />
            </div>

            {/* End Date */}
            <div className="space-y-2 flex-1 min-w-[200px]">
              <Label htmlFor="end-date">Bis</Label>
              <Input
                id="end-date"
                type="date"
                value={endDate}
                onChange={(e) => handleDateChange('end', e.target.value)}
              />
            </div>

            {/* Export */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="gap-2">
                  <FileDown className="w-4 h-4" />
                  Exportieren
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem
                  onClick={() => handleExport('xlsx')}
                  disabled={exportMutation.isPending}
                >
                  {exportMutation.isPending ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <FileDown className="w-4 h-4 mr-2" />
                  )}
                  Als Excel (.xlsx)
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => handleExport('csv')}
                  disabled={exportMutation.isPending}
                >
                  <FileDown className="w-4 h-4 mr-2" />
                  Als CSV (.csv)
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </CardContent>
      </Card>

      {/* Tabelle */}
      <Card>
        <CardHeader>
          <CardTitle>Verpasste Skonto-Rechnungen</CardTitle>
          <CardDescription>
            {data?.total || 0} Rechnung{data?.total !== 1 ? 'en' : ''} gefunden
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <TableSkeleton />
          ) : isError ? (
            <div className="text-center py-12">
              <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-destructive" />
              <p className="text-destructive font-medium">Fehler beim Laden</p>
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <TrendingDown className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>Keine verpassten Skonto-Fristen im gewählten Zeitraum</p>
            </div>
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Rechnung</TableHead>
                      <TableHead>Geschäftspartner</TableHead>
                      <TableHead className="text-right">Betrag</TableHead>
                      <TableHead className="text-right">Skonto %</TableHead>
                      <TableHead className="text-right">Verpasst</TableHead>
                      <TableHead>Frist</TableHead>
                      <TableHead>Verpasst um</TableHead>
                      <TableHead className="text-right">Bezahlt</TableHead>
                      <TableHead></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((item) => (
                      <MissedSkontoRow key={item.invoiceId} item={item} />
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Pagination */}
              {data.total > DEFAULT_PER_PAGE && (
                <div className="flex items-center justify-between mt-4">
                  <p className="text-sm text-muted-foreground">
                    Seite {data.page} von {Math.ceil(data.total / data.perPage)}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handlePageChange(data.page - 1)}
                      disabled={data.page === 1}
                    >
                      Zurück
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handlePageChange(data.page + 1)}
                      disabled={data.page >= Math.ceil(data.total / data.perPage)}
                    >
                      Weiter
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ==================== Sub-Components ====================

function StatsCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: string;
  icon: any;
  color: 'blue' | 'red' | 'yellow';
}) {
  const colorClasses = {
    blue: 'text-blue-600 bg-blue-50',
    red: 'text-red-600 bg-red-50',
    yellow: 'text-yellow-600 bg-yellow-50',
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardDescription className="flex items-center gap-2">
          <Icon className="w-4 h-4" />
          {title}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className={`text-2xl font-bold ${colorClasses[color].split(' ')[0]}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

function MissedSkontoRow({ item }: { item: any }) {
  const formattedAmount = new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(item.amount);

  const formattedSkontoAmount = new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(item.skontoAmount);

  const formattedDeadline = item.skontoDeadline
    ? new Date(item.skontoDeadline).toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      })
    : '-';

  const formattedPaidAt = item.paidAt
    ? new Date(item.paidAt).toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      })
    : '-';

  return (
    <TableRow>
      <TableCell className="font-medium">{item.invoiceNumber}</TableCell>
      <TableCell className="max-w-[200px] truncate">{item.entityName}</TableCell>
      <TableCell className="text-right font-mono">{formattedAmount}</TableCell>
      <TableCell className="text-right">{item.skontoPercentage}%</TableCell>
      <TableCell className="text-right font-semibold text-red-600">
        {formattedSkontoAmount}
      </TableCell>
      <TableCell>{formattedDeadline}</TableCell>
      <TableCell>
        <Badge variant="destructive">{item.daysMissedBy} Tage</Badge>
      </TableCell>
      <TableCell className="text-right text-sm text-muted-foreground">
        {formattedPaidAt}
      </TableCell>
      <TableCell>
        <Button variant="ghost" size="sm" asChild>
          <Link to="/invoices" search={{ invoiceId: item.invoiceId }}>
            <ExternalLink className="w-4 h-4" />
          </Link>
        </Button>
      </TableCell>
    </TableRow>
  );
}

function TableSkeleton() {
  return (
    <div className="space-y-3">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="flex gap-4">
          <Skeleton className="h-10 flex-1" />
          <Skeleton className="h-10 w-32" />
          <Skeleton className="h-10 w-24" />
        </div>
      ))}
    </div>
  );
}
