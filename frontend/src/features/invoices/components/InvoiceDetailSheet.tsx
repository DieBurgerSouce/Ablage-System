/**
 * InvoiceDetailSheet - Detail-Sidebar für einzelne Rechnung
 *
 * Zeigt alle Details einer Rechnung:
 * - Rechnungsnummer, Datum, Fälligkeit
 * - Betrag, Status, Mahnstufe
 * - Zahlungsinformationen
 * - Aktionsbuttons
 */

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  CheckCircle,
  TrendingUp,
  Calendar,
  Euro,
  FileText,
  Clock,
  AlertTriangle,
} from 'lucide-react';
import type { InvoiceTrackingResponse } from '../types/invoice-types';
import { UI_LABELS, STATUS_STYLES } from '../types/invoice-types';
import { DunningLevelBadge } from './DunningLevelBadge';

interface InvoiceDetailSheetProps {
  invoice: InvoiceTrackingResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onMarkPaid?: (invoice: InvoiceTrackingResponse) => void;
  onIncreaseDunning?: (invoice: InvoiceTrackingResponse) => void;
  isLoading?: boolean;
}

/**
 * Formatiert einen Betrag als Währung
 */
function formatCurrency(amount: number | null, currency: string = 'EUR'): string {
  if (amount === null) return '-';
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

/**
 * Formatiert ein Datum mit Uhrzeit
 */
function formatDateTime(dateString: string | null): string {
  if (!dateString) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(dateString));
}

export function InvoiceDetailSheet({
  invoice,
  open,
  onOpenChange,
  onMarkPaid,
  onIncreaseDunning,
  isLoading = false,
}: InvoiceDetailSheetProps) {
  if (!invoice) return null;

  const statusStyle = STATUS_STYLES[invoice.status];
  const isPaid = invoice.status === 'paid';
  const isCancelled = invoice.status === 'cancelled';
  const canMarkPaid = !isPaid && !isCancelled;
  const canIncreaseDunning = !isPaid && !isCancelled && invoice.dunningLevel < 4;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[400px] sm:w-[540px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            {invoice.invoiceNumber ?? 'Rechnungsverfolgung'}
          </SheetTitle>
          <SheetDescription>
            Details zur Rechnungsverfolgung
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-6">
          {/* Status-Bereich */}
          <div className="flex items-center gap-3">
            <Badge variant={statusStyle.variant} className="text-sm">
              {statusStyle.label}
            </Badge>
            <DunningLevelBadge level={invoice.dunningLevel} />
            {invoice.isOverdue && (
              <Badge variant="destructive" className="text-sm">
                <AlertTriangle className="h-3 w-3 mr-1" />
                {invoice.daysOverdue} Tage überfällig
              </Badge>
            )}
          </div>

          <Separator />

          {/* Rechnungsinformationen */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              Rechnungsinformationen
            </h3>

            <DetailRow
              icon={<FileText className="h-4 w-4" />}
              label="Rechnungsnummer"
              value={invoice.invoiceNumber ?? '-'}
            />
            <DetailRow
              icon={<Calendar className="h-4 w-4" />}
              label="Rechnungsdatum"
              value={formatDate(invoice.invoiceDate)}
            />
            <DetailRow
              icon={<Clock className="h-4 w-4" />}
              label="Fälligkeitsdatum"
              value={formatDate(invoice.dueDate)}
              valueClassName={invoice.isOverdue ? 'text-red-600 font-medium' : undefined}
            />
            <DetailRow
              icon={<Euro className="h-4 w-4" />}
              label="Betrag"
              value={formatCurrency(invoice.amount, invoice.currency)}
              valueClassName="font-mono font-medium"
            />
          </div>

          <Separator />

          {/* Zahlungsinformationen */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              Zahlungsinformationen
            </h3>

            <DetailRow
              icon={<CheckCircle className="h-4 w-4" />}
              label="Bezahlt am"
              value={formatDateTime(invoice.paidAt)}
            />
            <DetailRow
              icon={<Euro className="h-4 w-4" />}
              label="Gezahlter Betrag"
              value={formatCurrency(invoice.paidAmount, invoice.currency)}
              valueClassName="font-mono"
            />
            <DetailRow
              icon={<TrendingUp className="h-4 w-4" />}
              label="Letzte Mahnung"
              value={formatDateTime(invoice.lastDunningAt)}
            />
          </div>

          {/* Notizen */}
          {invoice.notes && (
            <>
              <Separator />
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                  Notizen
                </h3>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                  {invoice.notes}
                </p>
              </div>
            </>
          )}

          <Separator />

          {/* Metadaten */}
          <div className="space-y-2 text-xs text-muted-foreground">
            <p>Erstellt: {formatDateTime(invoice.createdAt)}</p>
            <p>Aktualisiert: {formatDateTime(invoice.updatedAt)}</p>
            <p className="font-mono">ID: {invoice.id}</p>
          </div>

          <Separator />

          {/* Aktionsbuttons */}
          <div className="flex gap-3">
            {canMarkPaid && onMarkPaid && (
              <Button
                className="flex-1"
                onClick={() => onMarkPaid(invoice)}
                disabled={isLoading}
              >
                <CheckCircle className="h-4 w-4 mr-2" />
                {UI_LABELS.actionMarkPaid}
              </Button>
            )}
            {canIncreaseDunning && onIncreaseDunning && (
              <Button
                variant="outline"
                className="flex-1 text-orange-600 border-orange-200 hover:bg-orange-50"
                onClick={() => onIncreaseDunning(invoice)}
                disabled={isLoading}
              >
                <TrendingUp className="h-4 w-4 mr-2" />
                {UI_LABELS.actionIncreaseDunning}
              </Button>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

interface DetailRowProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  valueClassName?: string;
}

function DetailRow({ icon, label, value, valueClassName }: DetailRowProps) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        {icon}
        {label}
      </div>
      <span className={`text-sm ${valueClassName ?? ''}`}>{value}</span>
    </div>
  );
}
