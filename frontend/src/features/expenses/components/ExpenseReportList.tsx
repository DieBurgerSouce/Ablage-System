/**
 * Expense Report List
 *
 * Liste aller Spesenabrechnungen mit Filterung und Status-Badges.
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Plus,
  MoreHorizontal,
  Eye,
  Edit,
  Send,
  CheckCircle2,
  XCircle,
  Wallet,
  Trash2,
  Filter,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useExpenseReports } from '../hooks/use-expense-queries';
import { formatCurrency, formatDate, formatStatus, getStatusColor } from '../utils/format';
import type { ExpenseReport, ExpenseReportStatus } from '@/types/models/expense';
import { cn } from '@/lib/utils';

interface ExpenseReportListProps {
  onSelect?: (report: ExpenseReport) => void;
  onEdit?: (report: ExpenseReport) => void;
  onCreate?: () => void;
  onSubmit?: (report: ExpenseReport) => void;
  onApprove?: (report: ExpenseReport) => void;
  onReject?: (report: ExpenseReport) => void;
  onPay?: (report: ExpenseReport) => void;
  onDelete?: (report: ExpenseReport) => void;
  className?: string;
}

const STATUS_OPTIONS: { value: ExpenseReportStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Alle Status' },
  { value: 'draft', label: 'Entwurf' },
  { value: 'submitted', label: 'Eingereicht' },
  { value: 'in_review', label: 'In Prüfung' },
  { value: 'approved', label: 'Genehmigt' },
  { value: 'rejected', label: 'Abgelehnt' },
  { value: 'paid', label: 'Ausgezahlt' },
];

const PAGE_SIZE = 20;

export function ExpenseReportList({
  onSelect,
  onEdit,
  onCreate,
  onSubmit,
  onApprove,
  onReject,
  onPay,
  onDelete,
  className,
}: ExpenseReportListProps) {
  const [page, setPage] = React.useState(0);
  const [statusFilter, setStatusFilter] = React.useState<ExpenseReportStatus | 'all'>('all');
  const [startDate, setStartDate] = React.useState<string>('');
  const [endDate, setEndDate] = React.useState<string>('');

  const { data: response, isLoading, error } = useExpenseReports({
    status: statusFilter === 'all' ? undefined : statusFilter,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  });

  const reports = response?.reports ?? [];
  const totalCount = response?.total ?? 0;
  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  // Reset page when filter changes
  React.useEffect(() => {
    setPage(0);
  }, [statusFilter, startDate, endDate]);

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Spesenabrechnungen</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Abrechnungen
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
            <CardTitle>Spesenabrechnungen</CardTitle>
            <CardDescription>
              {totalCount} {totalCount === 1 ? 'Abrechnung' : 'Abrechnungen'}
            </CardDescription>
          </div>
          {onCreate && (
            <Button onClick={onCreate}>
              <Plus className="mr-2 h-4 w-4" />
              Neue Abrechnung
            </Button>
          )}
        </div>

        {/* Filter */}
        <div className="flex flex-wrap gap-2 pt-4">
          <Select
            value={statusFilter}
            onValueChange={(v) => setStatusFilter(v as ExpenseReportStatus | 'all')}
          >
            <SelectTrigger className="w-[150px]">
              <Filter className="mr-2 h-4 w-4" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((opt) => (
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

          {(statusFilter !== 'all' || startDate || endDate) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setStatusFilter('all');
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
        ) : reports.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Keine Abrechnungen gefunden.{' '}
            {onCreate && (
              <Button variant="link" onClick={onCreate} className="px-0">
                Erste Abrechnung erstellen
              </Button>
            )}
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Titel</TableHead>
                  <TableHead>Zeitraum</TableHead>
                  <TableHead>Mitarbeiter</TableHead>
                  <TableHead className="text-right">Betrag</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Erstellt</TableHead>
                  <TableHead className="w-[50px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reports.map((report) => (
                  <ExpenseReportRow
                    key={report.id}
                    report={report}
                    onSelect={onSelect}
                    onEdit={onEdit}
                    onSubmit={onSubmit}
                    onApprove={onApprove}
                    onReject={onReject}
                    onPay={onPay}
                    onDelete={onDelete}
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
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Zurück
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={page >= totalPages - 1}
                  >
                    Weiter
                    <ChevronRight className="h-4 w-4" />
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

interface ExpenseReportRowProps {
  report: ExpenseReport;
  onSelect?: (report: ExpenseReport) => void;
  onEdit?: (report: ExpenseReport) => void;
  onSubmit?: (report: ExpenseReport) => void;
  onApprove?: (report: ExpenseReport) => void;
  onReject?: (report: ExpenseReport) => void;
  onPay?: (report: ExpenseReport) => void;
  onDelete?: (report: ExpenseReport) => void;
}

function ExpenseReportRow({
  report,
  onSelect,
  onEdit,
  onSubmit,
  onApprove,
  onReject,
  onPay,
  onDelete,
}: ExpenseReportRowProps) {
  const canEdit = report.status === 'draft' || report.status === 'rejected';
  const canSubmit = report.status === 'draft';
  const canApprove = report.status === 'submitted' || report.status === 'in_review';
  const canReject = report.status === 'submitted' || report.status === 'in_review';
  const canPay = report.status === 'approved';
  const canDelete = report.status === 'draft';

  return (
    <TableRow
      className={onSelect ? 'cursor-pointer hover:bg-muted/50' : undefined}
      onClick={() => onSelect?.(report)}
    >
      <TableCell className="font-medium">{report.title}</TableCell>
      <TableCell className="text-muted-foreground">
        {formatDate(report.period_start)} - {formatDate(report.period_end)}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {report.employee_name || '-'}
      </TableCell>
      <TableCell className="text-right font-mono">
        {formatCurrency(report.total_amount)}
      </TableCell>
      <TableCell>
        <Badge variant={getStatusColor(report.status)}>
          {formatStatus(report.status)}
        </Badge>
      </TableCell>
      <TableCell className="text-muted-foreground">
        {formatDate(report.created_at)}
      </TableCell>
      <TableCell>
        <DropdownMenu>
          <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <MoreHorizontal className="h-4 w-4" />
              <span className="sr-only">Aktionen</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onSelect?.(report)}>
              <Eye className="mr-2 h-4 w-4" />
              Anzeigen
            </DropdownMenuItem>

            {canEdit && onEdit && (
              <DropdownMenuItem onClick={() => onEdit(report)}>
                <Edit className="mr-2 h-4 w-4" />
                Bearbeiten
              </DropdownMenuItem>
            )}

            <DropdownMenuSeparator />

            {canSubmit && onSubmit && (
              <DropdownMenuItem onClick={() => onSubmit(report)}>
                <Send className="mr-2 h-4 w-4" />
                Einreichen
              </DropdownMenuItem>
            )}

            {canApprove && onApprove && (
              <DropdownMenuItem onClick={() => onApprove(report)}>
                <CheckCircle2 className="mr-2 h-4 w-4 text-green-600" />
                Genehmigen
              </DropdownMenuItem>
            )}

            {canReject && onReject && (
              <DropdownMenuItem onClick={() => onReject(report)}>
                <XCircle className="mr-2 h-4 w-4 text-destructive" />
                Ablehnen
              </DropdownMenuItem>
            )}

            {canPay && onPay && (
              <DropdownMenuItem onClick={() => onPay(report)}>
                <Wallet className="mr-2 h-4 w-4" />
                Auszahlen
              </DropdownMenuItem>
            )}

            {canDelete && onDelete && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => onDelete(report)}
                  className="text-destructive"
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Löschen
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </TableCell>
    </TableRow>
  );
}

export default ExpenseReportList;
