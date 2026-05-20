/**
 * Portal Dashboard
 *
 * Kundenportal Übersichtsseite mit KPIs, Schnellaktionen und aktuellen Rechnungen.
 */

import { Link } from '@tanstack/react-router';
import {
  FileText,
  AlertCircle,
  Clock,
  Euro,
  Plus,
  Upload,
  ArrowRight,
} from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  usePortalAuth,
  usePortalInvoiceSummary,
  usePortalOpenInvoices,
} from '../hooks/use-portal-queries';
import type { PortalInvoice } from '../types';
import { INVOICE_STATUS_LABELS, INVOICE_STATUS_COLORS } from '../types';

export function PortalDashboard() {
  const { user } = usePortalAuth();
  const { data: summary, isLoading: summaryLoading } = usePortalInvoiceSummary();
  const { data: openInvoices, isLoading: invoicesLoading } = usePortalOpenInvoices();

  const userName = user?.first_name || 'Kunde';

  return (
    <div className="space-y-8">
      {/* Welcome Section */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          Willkommen, {userName}!
        </h1>
        <p className="text-muted-foreground mt-1">
          Hier finden Sie eine Übersicht Ihrer Rechnungen und Dokumente.
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KPICard
          title="Offene Rechnungen"
          value={summary?.open_count}
          description={`${formatCurrency(summary?.open_amount)} offen`}
          icon={FileText}
          loading={summaryLoading}
        />
        <KPICard
          title="Überfällig"
          value={summary?.overdue_count}
          description={`${formatCurrency(summary?.overdue_amount)} überfällig`}
          icon={AlertCircle}
          loading={summaryLoading}
          variant="destructive"
        />
        <KPICard
          title="Bezahlt (Gesamt)"
          value={summary?.paid_count}
          description={`${formatCurrency(summary?.paid_amount)} bezahlt`}
          icon={Euro}
          loading={summaryLoading}
          variant="success"
        />
        <KPICard
          title="Rechnungen gesamt"
          value={summary?.total_count}
          description={`${formatCurrency(summary?.total_amount)} Gesamtvolumen`}
          icon={Clock}
          loading={summaryLoading}
        />
      </div>

      {/* Quick Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Schnellaktionen</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button asChild>
            <Link to="/portal/complaints">
              <Plus className="mr-2 h-4 w-4" />
              Neue Reklamation
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to="/portal/documents">
              <Upload className="mr-2 h-4 w-4" />
              Dokument hochladen
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to="/portal/messages">
              <ArrowRight className="mr-2 h-4 w-4" />
              Nachricht senden
            </Link>
          </Button>
        </CardContent>
      </Card>

      {/* Recent Invoices */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-lg">Offene Rechnungen</CardTitle>
            <CardDescription>
              Ihre aktuellen offenen Rechnungen
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/portal/invoices">
              Alle anzeigen
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </CardHeader>
        <CardContent>
          {invoicesLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : openInvoices?.items && openInvoices.items.length > 0 ? (
            <div className="space-y-3">
              {openInvoices.items.slice(0, 5).map((invoice: PortalInvoice) => (
                <InvoiceRow key={invoice.id} invoice={invoice} />
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <FileText className="mx-auto h-12 w-12 opacity-50 mb-3" />
              <p>Keine offenen Rechnungen vorhanden.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface KPICardProps {
  title: string;
  value?: number;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  loading?: boolean;
  variant?: 'default' | 'destructive' | 'success';
}

function KPICard({ title, value, description, icon: Icon, loading, variant = 'default' }: KPICardProps) {
  const variantStyles = {
    default: '',
    destructive: 'border-destructive/50',
    success: 'border-green-500/50',
  };

  return (
    <Card className={variantStyles[variant]}>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <div className="text-2xl font-bold">{value ?? 0}</div>
        )}
        <p className="text-xs text-muted-foreground mt-1">{description}</p>
      </CardContent>
    </Card>
  );
}

interface InvoiceRowProps {
  invoice: PortalInvoice;
}

function InvoiceRow({ invoice }: InvoiceRowProps) {
  return (
    <Link
      to="/portal/invoices/$id"
      params={{ id: invoice.id }}
      className="flex items-center justify-between p-4 rounded-lg border hover:bg-muted/50 transition-colors"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium truncate">{invoice.invoice_number}</span>
          <Badge className={INVOICE_STATUS_COLORS[invoice.status]} variant="secondary">
            {INVOICE_STATUS_LABELS[invoice.status]}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          Fällig am {formatDate(invoice.due_date)}
        </p>
      </div>
      <div className="text-right ml-4">
        <div className="font-semibold">{formatCurrency(invoice.outstanding_amount)}</div>
        <p className="text-xs text-muted-foreground">offen</p>
      </div>
    </Link>
  );
}

function formatCurrency(amount?: number): string {
  if (amount === undefined || amount === null) return '0,00 EUR';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

function formatDate(dateString: string): string {
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(dateString));
}

export default PortalDashboard;
