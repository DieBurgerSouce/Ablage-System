/**
 * CrossTenantDashboard
 *
 * Hauptkomponente für das mandantenübergreifende Admin-Dashboard.
 * Zeigt KPI-Karten, Dokumenten-Übersicht und Finanz-Tabelle.
 */

import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertTriangle, Building2, Activity, FileText, CalendarDays } from 'lucide-react';
import { useCompanyOverview, useCompanyFinancials } from '../hooks/useCrossTenantReports';
import { CompanyOverviewTable } from './CompanyOverviewTable';
import { CompanyFinancialTable } from './CompanyFinancialTable';

// =============================================================================
// Formatierung
// =============================================================================

const numberFormatter = new Intl.NumberFormat('de-DE');

function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

// =============================================================================
// KPI Card
// =============================================================================

interface KpiCardProps {
  title: string;
  value: string;
  icon: React.ElementType;
  description?: string;
}

function KpiCard({ title, value, icon: Icon, description }: KpiCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
      </CardContent>
    </Card>
  );
}

function KpiCardSkeleton() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-4" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-8 w-16" />
        <Skeleton className="mt-1 h-3 w-32" />
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Loading State
// =============================================================================

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-1 h-4 w-96" />
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KpiCardSkeleton />
        <KpiCardSkeleton />
        <KpiCardSkeleton />
        <KpiCardSkeleton />
      </div>
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    </div>
  );
}

// =============================================================================
// Error State
// =============================================================================

function DashboardError({ message }: { message: string }) {
  return (
    <Card className="p-8 text-center">
      <AlertTriangle className="mx-auto h-12 w-12 text-destructive" />
      <p className="mt-4 text-lg font-medium">Fehler beim Laden der Daten</p>
      <p className="text-muted-foreground">{message}</p>
    </Card>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function CrossTenantDashboard() {
  const {
    data: overviewData,
    isLoading: isLoadingOverview,
    error: overviewError,
  } = useCompanyOverview();

  const {
    data: financialData,
    isLoading: isLoadingFinancials,
    error: financialError,
  } = useCompanyFinancials();

  const isLoading = isLoadingOverview || isLoadingFinancials;
  const error = overviewError || financialError;

  // KPI-Berechnungen
  const totalDocuments = useMemo(() => {
    if (!overviewData) return 0;
    return overviewData.companies.reduce((sum, c) => sum + c.total_documents, 0);
  }, [overviewData]);

  const documentsThisMonth = useMemo(() => {
    if (!overviewData) return 0;
    return overviewData.companies.reduce((sum, c) => sum + c.documents_this_month, 0);
  }, [overviewData]);

  if (isLoading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Cross-Tenant Berichte</h1>
          <p className="text-muted-foreground">
            Mandantenübergreifende Statistiken und Analysen
          </p>
        </div>
        <DashboardError message={(error as Error).message} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Cross-Tenant Berichte</h1>
        <p className="text-muted-foreground">
          Mandantenübergreifende Statistiken und Analysen
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          title="Gesamte Firmen"
          value={formatNumber(overviewData?.total_companies ?? 0)}
          icon={Building2}
          description="Registrierte Mandanten"
        />
        <KpiCard
          title="Aktive Firmen"
          value={formatNumber(overviewData?.active_companies ?? 0)}
          icon={Activity}
          description={`von ${formatNumber(overviewData?.total_companies ?? 0)} gesamt`}
        />
        <KpiCard
          title="Gesamte Dokumente"
          value={formatNumber(totalDocuments)}
          icon={FileText}
          description="Über alle Mandanten"
        />
        <KpiCard
          title="Dokumente / Monat"
          value={formatNumber(documentsThisMonth)}
          icon={CalendarDays}
          description="Aktueller Monat"
        />
      </div>

      {/* Overview Table */}
      {overviewData && (
        <CompanyOverviewTable companies={overviewData.companies} />
      )}

      {/* Financial Table */}
      {financialData && (
        <CompanyFinancialTable companies={financialData.companies} />
      )}
    </div>
  );
}
