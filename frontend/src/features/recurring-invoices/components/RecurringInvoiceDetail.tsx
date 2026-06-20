/**
 * RecurringInvoiceDetail Component
 *
 * Detailansicht einer Abo-Rechnung mit Occurrence-Tabelle
 * und Kündigungsinformationen.
 */

import { ArrowLeft, Calendar, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useRecurringInvoice } from '../hooks/useRecurringInvoices';
import {
  INTERVAL_LABELS,
  STATUS_LABELS,
  STATUS_VARIANTS,
  OCCURRENCE_STATUS_LABELS,
  OCCURRENCE_STATUS_VARIANTS,
} from '../types/recurring-types';

// ==================== Props ====================

interface RecurringInvoiceDetailProps {
  recurringId: string;
  onBack: () => void;
}

// ==================== Helpers ====================

function formatEUR(amount: number | null): string {
  if (amount === null || amount === undefined) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(dateStr));
}

function formatDeviation(deviation: number | null): string {
  if (deviation === null || deviation === undefined) return '-';
  const prefix = deviation > 0 ? '+' : '';
  return `${prefix}${new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(deviation)}`;
}

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null;
  const target = new Date(dateStr);
  const now = new Date();
  const diff = Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  return diff;
}

// ==================== Component ====================

export default function RecurringInvoiceDetail({
  recurringId,
  onBack,
}: RecurringInvoiceDetailProps) {
  const { data: invoice, isLoading } = useRecurringInvoice(recurringId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        Abo-Rechnung nicht gefunden.
      </div>
    );
  }

  const cancellationDays = daysUntil(invoice.cancellation_deadline);

  return (
    <div className="space-y-6">
      {/* Zurück-Button */}
      <Button variant="ghost" onClick={onBack} className="gap-2">
        <ArrowLeft className="h-4 w-4" />
        Zurück zur Liste
      </Button>

      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle className="text-2xl">{invoice.vendor_name}</CardTitle>
              <CardDescription className="mt-1 flex items-center gap-3">
                <Badge variant="outline">
                  {INTERVAL_LABELS[invoice.interval_type]}
                </Badge>
                <Badge variant={STATUS_VARIANTS[invoice.status]}>
                  {STATUS_LABELS[invoice.status]}
                </Badge>
                <span>{formatEUR(invoice.expected_amount)} / Intervall</span>
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <p className="text-sm text-muted-foreground">Erster Nachweis</p>
              <p className="font-medium">{formatDate(invoice.first_seen_date)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Letzter Nachweis</p>
              <p className="font-medium">{formatDate(invoice.last_seen_date)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Nächste Fälligkeit</p>
              <p className="font-medium">{formatDate(invoice.next_expected_date)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Zuordnungen</p>
              <p className="font-medium">{invoice.match_count}</p>
            </div>
          </div>

          {/* Kategorie / Beschreibung */}
          {(invoice.category || invoice.description) && (
            <div className="mt-4 grid grid-cols-2 gap-4">
              {invoice.category && (
                <div>
                  <p className="text-sm text-muted-foreground">Kategorie</p>
                  <p className="font-medium">{invoice.category}</p>
                </div>
              )}
              {invoice.description && (
                <div>
                  <p className="text-sm text-muted-foreground">Beschreibung</p>
                  <p className="font-medium">{invoice.description}</p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Kündigungsinformationen */}
      {invoice.cancellation_deadline && (
        <Card
          className={
            cancellationDays !== null && cancellationDays <= 30
              ? 'border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-950'
              : ''
          }
        >
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4" />
              Kündigungsinformationen
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
              <div>
                <p className="text-sm text-muted-foreground">Kündigungsfrist</p>
                <p className="font-medium">{formatDate(invoice.cancellation_deadline)}</p>
              </div>
              {invoice.notice_period_days !== null && (
                <div>
                  <p className="text-sm text-muted-foreground">Kündigungsfrist (Tage)</p>
                  <p className="font-medium">{invoice.notice_period_days} Tage</p>
                </div>
              )}
              <div>
                <p className="text-sm text-muted-foreground">Automatische Verlängerung</p>
                <p className="font-medium">{invoice.auto_renewal ? 'Ja' : 'Nein'}</p>
              </div>
              {cancellationDays !== null && (
                <div>
                  <p className="text-sm text-muted-foreground">Verbleibende Tage</p>
                  <p className={`font-medium ${cancellationDays <= 14 ? 'text-red-600' : cancellationDays <= 30 ? 'text-orange-600' : ''}`}>
                    {cancellationDays > 0 ? `${cancellationDays} Tage` : 'Abgelaufen'}
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Occurrence-Tabelle (Soll/Ist) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Calendar className="h-4 w-4" />
            Soll/Ist-Verlauf
          </CardTitle>
          <CardDescription>
            {invoice.occurrences.length} Einträge
          </CardDescription>
        </CardHeader>
        <CardContent>
          {invoice.occurrences.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Soll-Datum</TableHead>
                  <TableHead className="text-right">Soll-Betrag</TableHead>
                  <TableHead>Ist-Datum</TableHead>
                  <TableHead className="text-right">Ist-Betrag</TableHead>
                  <TableHead className="text-right">Abweichung</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invoice.occurrences.map((occ) => (
                  <TableRow key={occ.id}>
                    <TableCell>{formatDate(occ.expected_date)}</TableCell>
                    <TableCell className="text-right">
                      {formatEUR(occ.expected_amount)}
                    </TableCell>
                    <TableCell>{formatDate(occ.actual_date)}</TableCell>
                    <TableCell className="text-right">
                      {formatEUR(occ.actual_amount)}
                    </TableCell>
                    <TableCell
                      className={`text-right ${
                        occ.amount_deviation !== null && occ.amount_deviation !== 0
                          ? occ.amount_deviation > 0
                            ? 'text-red-600'
                            : 'text-green-600'
                          : ''
                      }`}
                    >
                      {formatDeviation(occ.amount_deviation)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={OCCURRENCE_STATUS_VARIANTS[occ.status]}>
                        {OCCURRENCE_STATUS_LABELS[occ.status]}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="py-8 text-center text-muted-foreground">
              Noch keine Einträge vorhanden.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
