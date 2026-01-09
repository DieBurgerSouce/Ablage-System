/**
 * SpaceDetailPage - Bereichs-Detailansicht
 *
 * Zeigt alle Kategorien eines Bereichs als Tabs:
 * - Dokumente
 * - Immobilien
 * - Fahrzeuge
 * - Versicherungen
 * - Finanzen (Kredite + Anlagen)
 * - Fristen
 * - Notfallzugriff
 */

import * as React from 'react';
import { useParams, useNavigate, Link } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ArrowLeft,
  Building2,
  Car,
  Shield,
  Wallet,
  Calendar,
  AlertTriangle,
  FileText,
  Settings,
  Lock,
  Users,
  FolderOpen,
  HardDrive,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import { useSpace, useDeadlineWidget, useFinancialSummary } from '../hooks/use-privat-queries';
import { PropertiesPage } from './PropertiesPage';
import { VehiclesPage } from './VehiclesPage';
import { InsurancesPage } from './InsurancesPage';
import { FinancesPage } from './FinancesPage';
import { DeadlinesPage } from './DeadlinesPage';
import { EmergencyPage } from './EmergencyPage';
import { cn } from '@/lib/utils';
import type { PrivatDeadlineWidget, PrivatFinancialSummary, PrivatDeadlineWithStatus } from '@/types/privat';

const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

const formatCurrency = (value: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(value);
};

export function SpaceDetailPage() {
  const { spaceId } = useParams({ strict: false }) as { spaceId: string };
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = React.useState('overview');

  // Load space details
  const {
    data: space,
    isLoading: spaceLoading,
    error: spaceError,
  } = useSpace(spaceId);

  // Load additional data for overview
  const { data: deadlines } = useDeadlineWidget(spaceId);
  const { data: financial } = useFinancialSummary(spaceId);
// Calculate deadline counts from the widget data
  const overdueCount = deadlines?.overdue?.length ?? 0;
  const upcomingCount = (deadlines?.today?.length ?? 0) +
                        (deadlines?.thisWeek?.length ?? 0) +
                        (deadlines?.thisMonth?.length ?? 0);

  if (spaceLoading) {
    return (
      <div className="p-8 space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-48" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (spaceError || !space) {
    return (
      <div className="p-8">
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive">Fehler</CardTitle>
            <CardDescription>
              Der Bereich konnte nicht geladen werden. Bitte versuchen Sie es erneut.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" onClick={() => navigate({ to: '/privat' })}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Zurück zur Übersicht
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isPersonal = space.spaceType === 'personal';

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate({ to: '/privat' })}
            aria-label="Zurück zur Übersicht"
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div className="flex items-center gap-3">
            <div
              className={cn(
                'p-3 rounded-lg',
                isPersonal ? 'bg-purple-100 dark:bg-purple-950' : 'bg-blue-100 dark:bg-blue-950'
              )}
            >
              {isPersonal ? (
                <Lock className="h-6 w-6 text-purple-600 dark:text-purple-400" />
              ) : (
                <Users className="h-6 w-6 text-blue-600 dark:text-blue-400" />
              )}
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight">{space.name}</h1>
              {space.description && (
                <p className="text-muted-foreground">{space.description}</p>
              )}
            </div>
          </div>
        </div>
        <Button variant="outline" asChild>
          <Link to={`/privat/spaces/${spaceId}/settings` as string}>
            <Settings className="mr-2 h-4 w-4" />
            Einstellungen
          </Link>
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Dokumente</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{space.documentCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ordner</CardTitle>
            <FolderOpen className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{space.folderCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Speicher</CardTitle>
            <HardDrive className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatBytes(space.totalSizeBytes)}</div>
          </CardContent>
        </Card>
        {!isPersonal && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Nutzer</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{space.accessCount}</div>
            </CardContent>
          </Card>
        )}
        {upcomingCount > 0 && (
          <Card className="border-orange-200 dark:border-orange-800">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Anstehende Fristen</CardTitle>
              <Calendar className="h-4 w-4 text-orange-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-orange-600">{upcomingCount}</div>
              {overdueCount > 0 && (
                <p className="text-xs text-destructive">
                  {overdueCount} überfällig
                </p>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="grid w-full grid-cols-7 lg:w-auto lg:grid-cols-none lg:flex">
          <TabsTrigger value="overview" className="gap-2">
            <FileText className="h-4 w-4" />
            <span className="hidden sm:inline">Übersicht</span>
          </TabsTrigger>
          <TabsTrigger value="properties" className="gap-2">
            <Building2 className="h-4 w-4" />
            <span className="hidden sm:inline">Immobilien</span>
          </TabsTrigger>
          <TabsTrigger value="vehicles" className="gap-2">
            <Car className="h-4 w-4" />
            <span className="hidden sm:inline">Fahrzeuge</span>
          </TabsTrigger>
          <TabsTrigger value="insurances" className="gap-2">
            <Shield className="h-4 w-4" />
            <span className="hidden sm:inline">Versicherungen</span>
          </TabsTrigger>
          <TabsTrigger value="finances" className="gap-2">
            <Wallet className="h-4 w-4" />
            <span className="hidden sm:inline">Finanzen</span>
          </TabsTrigger>
          <TabsTrigger value="deadlines" className="gap-2">
            <Calendar className="h-4 w-4" />
            <span className="hidden sm:inline">Fristen</span>
          </TabsTrigger>
          <TabsTrigger value="emergency" className="gap-2">
            <AlertTriangle className="h-4 w-4" />
            <span className="hidden sm:inline">Notfall</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewSection
            financial={financial}
            overdueCount={overdueCount}
            upcomingCount={upcomingCount}
            deadlines={deadlines}
            onNavigate={setActiveTab}
          />
        </TabsContent>

        <TabsContent value="properties">
          <PropertiesPage spaceId={spaceId} />
        </TabsContent>

        <TabsContent value="vehicles">
          <VehiclesPage spaceId={spaceId} />
        </TabsContent>

        <TabsContent value="insurances">
          <InsurancesPage spaceId={spaceId} />
        </TabsContent>

        <TabsContent value="finances">
          <FinancesPage spaceId={spaceId} />
        </TabsContent>

        <TabsContent value="deadlines">
          <DeadlinesPage spaceId={spaceId} />
        </TabsContent>

        <TabsContent value="emergency">
          <EmergencyPage spaceId={spaceId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

interface OverviewSectionProps {
  financial?: PrivatFinancialSummary;
  deadlines?: PrivatDeadlineWidget;
  overdueCount: number;
  upcomingCount: number;
  onNavigate: (tab: string) => void;
}

function OverviewSection({ financial, deadlines, overdueCount, upcomingCount, onNavigate }: OverviewSectionProps) {
  // Combine all deadline items for display
  const allDeadlines: PrivatDeadlineWithStatus[] = [
    ...(deadlines?.overdue ?? []),
    ...(deadlines?.today ?? []),
    ...(deadlines?.thisWeek ?? []),
    ...(deadlines?.thisMonth ?? []),
  ];

  return (
    <div className="grid gap-6 md:grid-cols-2">
      {/* Quick Actions */}
      <Card>
        <CardHeader>
          <CardTitle>Schnellzugriff</CardTitle>
          <CardDescription>Häufig genutzte Aktionen</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <Button variant="outline" className="justify-start" onClick={() => onNavigate('properties')}>
            <Building2 className="mr-2 h-4 w-4" />
            Immobilien verwalten
          </Button>
          <Button variant="outline" className="justify-start" onClick={() => onNavigate('vehicles')}>
            <Car className="mr-2 h-4 w-4" />
            Fahrzeuge verwalten
          </Button>
          <Button variant="outline" className="justify-start" onClick={() => onNavigate('insurances')}>
            <Shield className="mr-2 h-4 w-4" />
            Versicherungen verwalten
          </Button>
          <Button variant="outline" className="justify-start" onClick={() => onNavigate('finances')}>
            <Wallet className="mr-2 h-4 w-4" />
            Finanzen verwalten
          </Button>
        </CardContent>
      </Card>

      {/* Financial Summary */}
      {financial && (
        <Card>
          <CardHeader>
            <CardTitle>Finanzübersicht</CardTitle>
            <CardDescription>Aktuelle Vermögenslage</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Investitionen</span>
              <span className="font-semibold text-green-600">
                {formatCurrency(financial.totalInvestments)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Kredite</span>
              <span className="font-semibold text-red-600">
                {formatCurrency(financial.totalLoans)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Monatl. Kreditraten</span>
              <span className="font-medium">
                {formatCurrency(financial.monthlyLoanPayments)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Jährl. Versicherung</span>
              <span className="font-medium">
                {formatCurrency(financial.annualInsuranceCost)}
              </span>
            </div>
            <div className="border-t pt-4">
              <div className="flex justify-between items-center">
                <span className="font-medium">Nettovermögen</span>
                <span className={cn(
                  'text-xl font-bold',
                  financial.netWorth >= 0 ? 'text-green-600' : 'text-red-600'
                )}>
                  {formatCurrency(financial.netWorth)}
                </span>
              </div>
              {financial.investmentReturnPercentage !== 0 && (
                <div className="flex items-center justify-end gap-1 mt-1">
                  {financial.investmentReturnPercentage > 0 ? (
                    <TrendingUp className="h-4 w-4 text-green-600" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-red-600" />
                  )}
                  <span className={cn(
                    'text-sm',
                    financial.investmentReturnPercentage > 0 ? 'text-green-600' : 'text-red-600'
                  )}>
                    {financial.investmentReturnPercentage > 0 ? '+' : ''}{financial.investmentReturnPercentage.toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Upcoming Deadlines */}
      {allDeadlines.length > 0 && (
        <Card className="md:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Anstehende Fristen</CardTitle>
              <CardDescription>
                {overdueCount > 0 && (
                  <span className="text-destructive mr-1">
                    {overdueCount} überfällig
                  </span>
                )}
                {upcomingCount} anstehend
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={() => onNavigate('deadlines')}>
              Alle anzeigen
            </Button>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {allDeadlines.slice(0, 5).map((deadline) => (
                <div
                  key={deadline.id}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                >
                  <div className="flex items-center gap-3">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                    <span>{deadline.title}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">
                      {new Date(deadline.dueDate).toLocaleDateString('de-DE')}
                    </span>
                    <Badge
                      variant={deadline.isOverdue ? 'destructive' : 'secondary'}
                    >
                      {deadline.isOverdue ? 'Überfällig' :
                       deadline.daysRemaining === 0 ? 'Heute fällig' :
                       deadline.daysRemaining <= 7 ? 'Bald fällig' : 'Anstehend'}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default SpaceDetailPage;
