/**
 * InvoiceTable - Rechnungs-Tabelle
 *
 * Spalten:
 * - Rechnungsnr.
 * - Geschäftspartner (Link zu Entity)
 * - Betrag + Währung
 * - Fällig am
 * - Status Badge
 * - Mahnstufe Badge (0-4)
 * - Tage überfällig
 * - Actions Dropdown
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import type { InvoiceTrackingResponse } from '../types/invoice-types';
import { UI_LABELS, STATUS_STYLES } from '../types/invoice-types';
import { DunningLevelBadge } from './DunningLevelBadge';
import { InvoiceActions } from './InvoiceActions';

interface InvoiceTableProps {
  invoices: InvoiceTrackingResponse[];
  isLoading?: boolean;
  onRowClick?: (invoice: InvoiceTrackingResponse) => void;
  onMarkPaid?: (invoice: InvoiceTrackingResponse) => void;
  onIncreaseDunning?: (invoice: InvoiceTrackingResponse) => void;
}

/**
 * Formatiert einen Betrag als Währung
 */
function formatCurrency(amount: number, currency: string = 'EUR'): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency,
  }).format(amount);
}

/**
 * Formatiert ein Datum
 */
function formatDate(dateString: string | null): string {
  if (!dateString) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(dateString));
}

export function InvoiceTable({
  invoices,
  isLoading = false,
  onRowClick,
  onMarkPaid,
  onIncreaseDunning,
}: InvoiceTableProps) {
  if (isLoading) {
    return <InvoiceTableSkeleton />;
  }

  if (invoices.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        Keine Rechnungen gefunden
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{UI_LABELS.tableInvoiceNumber}</TableHead>
            <TableHead className="text-right">{UI_LABELS.tableAmount}</TableHead>
            <TableHead>{UI_LABELS.tableDueDate}</TableHead>
            <TableHead>{UI_LABELS.tableStatus}</TableHead>
            <TableHead>{UI_LABELS.tableDunningLevel}</TableHead>
            <TableHead className="text-right">{UI_LABELS.tableDaysOverdue}</TableHead>
            <TableHead className="w-[50px]"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {invoices.map((invoice) => (
            <InvoiceTableRow
              key={invoice.id}
              invoice={invoice}
              onClick={onRowClick}
              onMarkPaid={onMarkPaid}
              onIncreaseDunning={onIncreaseDunning}
            />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

interface InvoiceTableRowProps {
  invoice: InvoiceTrackingResponse;
  onClick?: (invoice: InvoiceTrackingResponse) => void;
  onMarkPaid?: (invoice: InvoiceTrackingResponse) => void;
  onIncreaseDunning?: (invoice: InvoiceTrackingResponse) => void;
}

function InvoiceTableRow({
  invoice,
  onClick,
  onMarkPaid,
  onIncreaseDunning,
}: InvoiceTableRowProps) {
  const statusStyle = STATUS_STYLES[invoice.status];
  const isClickable = !!onClick;

  return (
    <TableRow
      className={cn(
        isClickable && 'cursor-pointer hover:bg-muted/50',
        invoice.isOverdue && 'bg-red-50/50 dark:bg-red-950/20'
      )}
      onClick={() => onClick?.(invoice)}
    >
      <TableCell className="font-medium">
        {invoice.invoiceNumber ?? '-'}
      </TableCell>
      <TableCell className="text-right font-mono">
        {formatCurrency(invoice.amount, invoice.currency)}
      </TableCell>
      <TableCell>{formatDate(invoice.dueDate)}</TableCell>
      <TableCell>
        <Badge variant={statusStyle.variant}>
          {statusStyle.label}
        </Badge>
      </TableCell>
      <TableCell>
        <DunningLevelBadge level={invoice.dunningLevel} />
      </TableCell>
      <TableCell className="text-right">
        {invoice.isOverdue ? (
          <span className="text-red-600 font-medium">
            {invoice.daysOverdue} Tage
          </span>
        ) : (
          <span className="text-muted-foreground">-</span>
        )}
      </TableCell>
      <TableCell onClick={(e) => e.stopPropagation()}>
        <InvoiceActions
          invoice={invoice}
          onMarkPaid={onMarkPaid}
          onIncreaseDunning={onIncreaseDunning}
          onViewDetails={onClick}
        />
      </TableCell>
    </TableRow>
  );
}

function InvoiceTableSkeleton() {
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{UI_LABELS.tableInvoiceNumber}</TableHead>
            <TableHead className="text-right">{UI_LABELS.tableAmount}</TableHead>
            <TableHead>{UI_LABELS.tableDueDate}</TableHead>
            <TableHead>{UI_LABELS.tableStatus}</TableHead>
            <TableHead>{UI_LABELS.tableDunningLevel}</TableHead>
            <TableHead className="text-right">{UI_LABELS.tableDaysOverdue}</TableHead>
            <TableHead className="w-[50px]"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[1, 2, 3, 4, 5].map((i) => (
            <TableRow key={i}>
              <TableCell><Skeleton className="h-4 w-24" /></TableCell>
              <TableCell><Skeleton className="h-4 w-20 ml-auto" /></TableCell>
              <TableCell><Skeleton className="h-4 w-24" /></TableCell>
              <TableCell><Skeleton className="h-5 w-16" /></TableCell>
              <TableCell><Skeleton className="h-5 w-20" /></TableCell>
              <TableCell><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
              <TableCell><Skeleton className="h-8 w-8" /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
