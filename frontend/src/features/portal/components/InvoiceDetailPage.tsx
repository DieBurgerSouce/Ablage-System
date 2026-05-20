/**
 * Invoice Detail Page
 *
 * Detailansicht einer Rechnung mit Zahlungshistorie und Aktionen.
 */

import { useParams, Link } from '@tanstack/react-router';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  ArrowLeft,
  Download,
  AlertTriangle,
  CheckCircle,
  Clock,
  Euro,
  Calendar,
  Percent,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
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
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from '@/components/ui/alert';
import { usePortalInvoiceDetail, usePortalPayments } from '../hooks/use-portal-queries';
import type { PortalPayment } from '../types';
import {
  INVOICE_STATUS_LABELS,
  INVOICE_STATUS_COLORS,
  PAYMENT_STATUS_LABELS,
  PAYMENT_STATUS_COLORS,
} from '../types';

export function InvoiceDetailPage() {
  const { id } = useParams({ from: '/portal/invoices/$id' });
  const { data: invoice, isLoading, isError, error } = usePortalInvoiceDetail(id);
  const { data: payments } = usePortalPayments({ invoice_tracking_id: id });

  if (isLoading) {
    return <InvoiceDetailSkeleton />;
  }

  if (isError || !invoice) {
    return (
      <div className="space-y-6">
        <BackButton />
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Fehler</AlertTitle>
          <AlertDescription>
            {(error as Error)?.message || 'Rechnung konnte nicht geladen werden.'}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const hasSkonto = invoice.skonto_percentage && invoice.skonto_deadline;
  const skontoExpired = hasSkonto && new Date(invoice.skonto_deadline!) < new Date();

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <BackButton />

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight">
              {invoice.invoice_number}
            </h1>
            <Badge className={INVOICE_STATUS_COLORS[invoice.status]} variant="secondary">
              {INVOICE_STATUS_LABELS[invoice.status]}
            </Badge>
          </div>
          <p className="text-muted-foreground mt-1">
            {invoice.description || 'Rechnung'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <Link to="/portal/complaints" search={{ invoice_id: invoice.id }}>
              <AlertTriangle className="mr-2 h-4 w-4" />
              Reklamation
            </Link>
          </Button>
          {invoice.document_id && (
            <Button>
              <Download className="mr-2 h-4 w-4" />
              PDF herunterladen
            </Button>
          )}
        </div>
      </div>

      {/* Overdue Warning */}
      {invoice.status === 'overdue' && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Zahlungsverzug</AlertTitle>
          <AlertDescription>
            Diese Rechnung ist überfällig. Bitte überweisen Sie den ausstehenden Betrag umgehend.
          </AlertDescription>
        </Alert>
      )}

      {/* Skonto Info */}
      {hasSkonto && !skontoExpired && (
        <Alert>
          <Percent className="h-4 w-4" />
          <AlertTitle>Skonto verfügbar</AlertTitle>
          <AlertDescription>
            Bei Zahlung bis {formatDate(invoice.skonto_deadline!)} erhalten Sie {invoice.skonto_percentage}% Skonto
            ({formatCurrency(invoice.skonto_amount || 0)} Ersparnis).
          </AlertDescription>
        </Alert>
      )}

      {/* Main Content Grid */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Invoice Details */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Rechnungsdetails</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <DetailRow icon={Calendar} label="Rechnungsdatum" value={formatDate(invoice.invoice_date)} />
            <DetailRow icon={Clock} label="Fällig am" value={formatDate(invoice.due_date)} />
            <Separator />
            <DetailRow icon={Euro} label="Rechnungsbetrag" value={formatCurrency(invoice.amount)} highlight />
            {invoice.outstanding_amount !== invoice.amount && (
              <DetailRow icon={Euro} label="Ausstehend" value={formatCurrency(invoice.outstanding_amount)} highlight />
            )}
            {invoice.dunning_level && invoice.dunning_level > 0 && (
              <DetailRow icon={AlertTriangle} label="Mahnstufe" value={`${invoice.dunning_level}. Mahnung`} />
            )}
          </CardContent>
        </Card>

        {/* Summary Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Zahlungsübersicht</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Rechnungsbetrag</span>
                <span className="font-medium">{formatCurrency(invoice.amount)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Bereits bezahlt</span>
                <span className="font-medium text-green-600">
                  -{formatCurrency(invoice.amount - invoice.outstanding_amount)}
                </span>
              </div>
              <Separator />
              <div className="flex justify-between items-center">
                <span className="font-semibold">Ausstehend</span>
                <span className="font-bold text-xl">{formatCurrency(invoice.outstanding_amount)}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Payment History */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Zahlungshistorie</CardTitle>
          <CardDescription>
            Alle gemeldeten Zahlungen zu dieser Rechnung
          </CardDescription>
        </CardHeader>
        <CardContent>
          {payments?.items && payments.items.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Datum</TableHead>
                  <TableHead>Betrag</TableHead>
                  <TableHead>Referenz</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {payments.items.map((payment: PortalPayment) => (
                  <TableRow key={payment.id}>
                    <TableCell>{formatDate(payment.payment_date)}</TableCell>
                    <TableCell className="font-medium">
                      {formatCurrency(parseFloat(payment.payment_amount))}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {payment.payment_reference || '-'}
                    </TableCell>
                    <TableCell>
                      <Badge
                        className={PAYMENT_STATUS_COLORS[payment.status]}
                        variant="secondary"
                      >
                        {PAYMENT_STATUS_LABELS[payment.status]}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <CheckCircle className="mx-auto h-12 w-12 opacity-50 mb-3" />
              <p>Noch keine Zahlungen gemeldet.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function BackButton() {
  return (
    <Button variant="ghost" size="sm" asChild>
      <Link to="/portal/invoices">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Zurück zur Übersicht
      </Link>
    </Button>
  );
}

interface DetailRowProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  highlight?: boolean;
}

function DetailRow({ icon: Icon, label, value, highlight }: DetailRowProps) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
        <span>{label}</span>
      </div>
      <span className={highlight ? 'font-semibold' : ''}>{value}</span>
    </div>
  );
}

function InvoiceDetailSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-32" />
      <div className="flex justify-between">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-10 w-40" />
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
      <Skeleton className="h-48" />
    </div>
  );
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

function formatDate(dateString: string): string {
  return format(new Date(dateString), 'dd.MM.yyyy', { locale: de });
}

export default InvoiceDetailPage;
