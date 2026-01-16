/**
 * InvoiceTrackingBanner - Zahlungsstatus-Uebersicht fuer Rechnungen
 *
 * Zeigt eine Zusammenfassung des Zahlungsstatus:
 * - Offene Rechnungen (heute)
 * - Bald faellig (diese Woche)
 * - Ueberfaellig (kritisch)
 * - Gesamtbetrag und offener Betrag
 * - Skonto-Hinweis (falls verfuegbar)
 */

import { useMemo } from 'react';
import {
  AlertTriangle,
  Clock,
  DollarSign,
  TrendingDown,
  Calendar,
  Percent,
  ChevronRight,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import type { CategoryDocumentAggregations, CategoryDocumentResponse } from '../types';

// ==================== Types ====================

interface InvoiceTrackingBannerProps {
  aggregations: CategoryDocumentAggregations | undefined;
  documents: CategoryDocumentResponse[];
  isLoading?: boolean;
  onFilterOverdue?: () => void;
  onFilterDueSoon?: () => void;
  onFilterOpen?: () => void;
}

interface SkontoOpportunity {
  documentId: string;
  documentNumber: string;
  amount: number;
  skontoPercent: number;
  skontoSaving: number;
  daysRemaining: number;
}

// ==================== Helper Functions ====================

/**
 * Formatiert einen Betrag als Waehrung (EUR)
 */
function formatCurrency(amount: number, currency = 'EUR'): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

/**
 * Berechnet Tage bis zum Faelligkeitsdatum
 */
function daysUntilDue(dueDate: string | null): number | null {
  if (!dueDate) return null;
  const due = new Date(dueDate);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);
  return Math.ceil((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

/**
 * Findet Skonto-Moeglichkeiten in den Dokumenten
 * Verwendet echte Skonto-Daten aus der OCR-Extraktion
 */
function findSkontoOpportunities(documents: CategoryDocumentResponse[]): SkontoOpportunity[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  return documents
    .filter((doc) => {
      // Nur offene Rechnungen mit Skonto-Daten beruecksichtigen
      if (doc.paymentStatus !== 'offen') return false;
      if (!doc.skontoPercent || doc.skontoPercent <= 0) return false;

      // Skonto-Deadline pruefen (falls vorhanden)
      if (doc.skontoDeadline) {
        const deadline = new Date(doc.skontoDeadline);
        deadline.setHours(0, 0, 0, 0);
        // Nur wenn Deadline noch nicht abgelaufen
        if (deadline < today) return false;
      } else if (doc.skontoDays && doc.dueDate) {
        // Fallback: Berechne Skonto-Deadline aus skontoDays
        const dueDate = new Date(doc.dueDate);
        const invoiceDate = doc.documentDate ? new Date(doc.documentDate) : new Date(doc.createdAt);
        const skontoDeadline = new Date(invoiceDate);
        skontoDeadline.setDate(skontoDeadline.getDate() + doc.skontoDays);
        if (skontoDeadline < today) return false;
      }

      return true;
    })
    .slice(0, 3) // Max 3 Skonto-Hinweise
    .map((doc) => {
      // Berechne verbleibende Tage bis Skonto-Deadline
      let daysRemaining = 0;
      if (doc.skontoDeadline) {
        const deadline = new Date(doc.skontoDeadline);
        daysRemaining = Math.ceil((deadline.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
      } else if (doc.skontoDays && doc.documentDate) {
        const invoiceDate = new Date(doc.documentDate);
        const skontoDeadline = new Date(invoiceDate);
        skontoDeadline.setDate(skontoDeadline.getDate() + doc.skontoDays);
        daysRemaining = Math.ceil((skontoDeadline.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
      }

      // Berechne Skonto-Ersparnis
      const skontoSaving = doc.skontoAmount
        || (doc.totalAmount && doc.skontoPercent
            ? (doc.totalAmount * doc.skontoPercent) / 100
            : 0);

      return {
        documentId: doc.id,
        documentNumber: doc.documentNumber || doc.filename,
        amount: doc.totalAmount || 0,
        skontoPercent: doc.skontoPercent || 0,
        skontoSaving,
        daysRemaining: Math.max(0, daysRemaining),
      };
    });
}

// ==================== Sub-Components ====================

function StatCard({
  icon: Icon,
  label,
  value,
  subLabel,
  variant = 'default',
  onClick,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  subLabel?: string;
  variant?: 'default' | 'warning' | 'danger' | 'success';
  onClick?: () => void;
}) {
  const variantStyles = {
    default: 'bg-muted/50 text-foreground',
    warning: 'bg-yellow-50 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200',
    danger: 'bg-red-50 text-red-800 dark:bg-red-900/30 dark:text-red-200',
    success: 'bg-green-50 text-green-800 dark:bg-green-900/30 dark:text-green-200',
  };

  const iconStyles = {
    default: 'text-muted-foreground',
    warning: 'text-yellow-600 dark:text-yellow-400',
    danger: 'text-red-600 dark:text-red-400',
    success: 'text-green-600 dark:text-green-400',
  };

  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        'flex flex-col items-start p-3 rounded-lg transition-all min-w-[100px]',
        variantStyles[variant],
        onClick && 'hover:scale-105 hover:shadow-md cursor-pointer'
      )}
    >
      <div className="flex items-center gap-2 mb-1">
        <Icon className={cn('w-4 h-4', iconStyles[variant])} />
        <span className="text-xs font-medium opacity-80">{label}</span>
      </div>
      <span className="text-lg font-bold">{value}</span>
      {subLabel && <span className="text-xs opacity-70">{subLabel}</span>}
    </button>
  );
}

function SkontoAlert({
  opportunities,
  totalSaving,
}: {
  opportunities: SkontoOpportunity[];
  totalSaving: number;
}) {
  if (opportunities.length === 0) return null;

  return (
    <div className="flex items-center justify-between p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-green-100 dark:bg-green-800 rounded-full">
          <Percent className="w-4 h-4 text-green-600 dark:text-green-400" />
        </div>
        <div>
          <p className="text-sm font-medium text-green-800 dark:text-green-200">
            Skonto möglich: {opportunities.length} Rechnung{opportunities.length > 1 ? 'en' : ''}
          </p>
          <p className="text-xs text-green-600 dark:text-green-400">
            Mögliche Ersparnis: {formatCurrency(totalSaving)}
          </p>
        </div>
      </div>
      <Button variant="ghost" size="sm" className="text-green-700 dark:text-green-300">
        Details
        <ChevronRight className="w-4 h-4 ml-1" />
      </Button>
    </div>
  );
}

// ==================== Loading State ====================

function InvoiceTrackingBannerSkeleton() {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-4">
          <Skeleton className="w-5 h-5 rounded" />
          <Skeleton className="h-5 w-32" />
        </div>
        <div className="flex flex-wrap gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20 w-28 rounded-lg" />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Main Component ====================

export function InvoiceTrackingBanner({
  aggregations,
  documents,
  isLoading,
  onFilterOverdue,
  onFilterDueSoon,
  onFilterOpen,
}: InvoiceTrackingBannerProps) {
  // Berechne Statistiken
  const stats = useMemo(() => {
    if (!aggregations) {
      return {
        openCount: 0,
        dueSoonCount: 0,
        overdueCount: 0,
        totalAmount: 0,
        openAmount: 0,
        paidAmount: 0,
      };
    }

    // Zaehle "bald faellig" (naechste 7 Tage) aus Dokumenten
    const dueSoonCount = documents.filter((doc) => {
      if (doc.paymentStatus !== 'offen') return false;
      const days = daysUntilDue(doc.dueDate);
      return days !== null && days > 0 && days <= 7;
    }).length;

    return {
      openCount: aggregations.documentsByPaymentStatus?.offen || 0,
      dueSoonCount,
      overdueCount: aggregations.overdueCount || 0,
      totalAmount: aggregations.totalAmount || 0,
      openAmount: aggregations.totalOpen || 0,
      paidAmount: aggregations.totalPaid || 0,
    };
  }, [aggregations, documents]);

  // Finde Skonto-Moeglichkeiten
  const skontoOpportunities = useMemo(() => findSkontoOpportunities(documents), [documents]);
  const totalSkontoSaving = skontoOpportunities.reduce((sum, o) => sum + o.skontoSaving, 0);

  // Loading State
  if (isLoading) {
    return <InvoiceTrackingBannerSkeleton />;
  }

  // Keine Daten
  if (!aggregations || stats.totalAmount === 0) {
    return null;
  }

  return (
    <Card data-testid="invoice-tracking-banner" className="border-l-4 border-l-blue-500">
      <CardContent className="p-4 space-y-4">
        {/* Header */}
        <div className="flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-blue-500" />
          <h3 className="font-semibold text-foreground">Zahlungsstatus</h3>
          {stats.overdueCount > 0 && (
            <Badge variant="destructive" className="ml-2">
              {stats.overdueCount} überfällig
            </Badge>
          )}
        </div>

        {/* Stats Grid */}
        <div className="flex flex-wrap gap-4">
          <StatCard
            icon={Clock}
            label="Offen"
            value={stats.openCount}
            subLabel="heute"
            variant="default"
            onClick={onFilterOpen}
          />
          <StatCard
            icon={Calendar}
            label="Bald faellig"
            value={stats.dueSoonCount}
            subLabel="diese Woche"
            variant={stats.dueSoonCount > 0 ? 'warning' : 'default'}
            onClick={onFilterDueSoon}
          />
          <StatCard
            icon={AlertTriangle}
            label="Ueberfaellig"
            value={stats.overdueCount}
            subLabel={stats.overdueCount > 0 ? 'KRITISCH' : '-'}
            variant={stats.overdueCount > 0 ? 'danger' : 'default'}
            onClick={onFilterOverdue}
          />
          <StatCard
            icon={TrendingDown}
            label="Gesamt"
            value={formatCurrency(stats.totalAmount)}
            subLabel={`davon offen: ${formatCurrency(stats.openAmount)}`}
            variant="default"
          />
        </div>

        {/* Skonto Alert */}
        <SkontoAlert opportunities={skontoOpportunities} totalSaving={totalSkontoSaving} />
      </CardContent>
    </Card>
  );
}

export default InvoiceTrackingBanner;
