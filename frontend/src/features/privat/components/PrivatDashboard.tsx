/**
 * PrivatDashboard - Übersichtsseite für den Privat-Bereich
 *
 * Zeigt Statistiken, kommende Fristen und schnelle Aktionen
 */

import * as React from 'react';
import { Link } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Lock, Home, Car, Shield, TrendingUp, Calendar, AlertTriangle, ArrowRight, FileText, Clock, Euro } from 'lucide-react';
import type {
  PrivatDashboardStats,
  PrivatFinancialSummary,
  PrivatDeadlineWidget,
  PrivatDeadlineWithStatus,
} from '@/types/privat';
import { cn } from '@/lib/utils';
import {
  FinancialHealthDashboard,
  RecommendationsPanel,
  NetWorthChart,
} from './intelligence';

interface PrivatDashboardProps {
  stats?: PrivatDashboardStats;
  financial?: PrivatFinancialSummary;
  deadlines?: PrivatDeadlineWidget;
  isLoading?: boolean;
  error?: Error | null;
  className?: string;
  spaceId?: string;
}

const formatCurrency = (amount: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
};

const formatDate = (dateStr: string): string => {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

export function PrivatDashboard({
  stats,
  financial,
  deadlines,
  isLoading,
  error,
  className,
  spaceId,
}: PrivatDashboardProps) {
  // Helper: Link mit optionalem space Query-Parameter
  const buildLink = (basePath: string): string => {
    return spaceId ? `${basePath}?space=${spaceId}` : basePath;
  };
  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Privat-Übersicht</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Daten
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-950">
            <Lock className="h-6 w-6 text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Privat</h1>
            <p className="text-muted-foreground">
              Ihre persönliche Dokumentenverwaltung
            </p>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Dokumente"
          value={stats?.totalDocuments ?? 0}
          icon={<FileText className="h-4 w-4 text-blue-500" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Immobilien"
          value={stats?.totalProperties ?? 0}
          icon={<Home className="h-4 w-4 text-green-500" />}
          link={buildLink('/privat/immobilien')}
          isLoading={isLoading}
        />
        <StatCard
          title="Fahrzeuge"
          value={stats?.totalVehicles ?? 0}
          icon={<Car className="h-4 w-4 text-orange-500" />}
          link={buildLink('/privat/fahrzeuge')}
          isLoading={isLoading}
        />
        <StatCard
          title="Versicherungen"
          value={stats?.totalInsurances ?? 0}
          icon={<Shield className="h-4 w-4 text-red-500" />}
          link={buildLink('/privat/versicherungen')}
          isLoading={isLoading}
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Financial Summary */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Euro className="h-5 w-5 text-green-500" />
              Finanzübersicht
            </CardTitle>
            <CardDescription>Ihre Vermögensposition auf einen Blick</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-16" />
                ))}
              </div>
            ) : financial ? (
              <div className="grid gap-4 md:grid-cols-2">
                <FinancialItem
                  label="Nettovermögen"
                  value={formatCurrency(financial.netWorth)}
                  positive={financial.netWorth >= 0}
                  large
                />
                <FinancialItem
                  label="Gesamt Investments"
                  value={formatCurrency(financial.totalInvestments)}
                  positive
                />
                <FinancialItem
                  label="Gesamt Kredite"
                  value={formatCurrency(financial.totalLoans)}
                  positive={false}
                />
                <FinancialItem
                  label="Monatl. Kreditraten"
                  value={formatCurrency(financial.monthlyLoanPayments)}
                />
                <FinancialItem
                  label="Jährl. Versicherungen"
                  value={formatCurrency(financial.annualInsuranceCost)}
                />
                <FinancialItem
                  label="Investment-Rendite"
                  value={`${financial.investmentReturnPercentage.toFixed(2)}%`}
                  positive={financial.investmentReturnPercentage >= 0}
                />
              </div>
            ) : (
              <p className="text-center py-8 text-muted-foreground">
                Keine Finanzdaten vorhanden
              </p>
            )}
          </CardContent>
        </Card>

        {/* Upcoming Deadlines */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Calendar className="h-5 w-5 text-amber-500" />
                Fristen
              </CardTitle>
              <Link to={buildLink('/privat/fristen')}>
                <Button variant="ghost" size="sm">
                  Alle
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : deadlines ? (
              <div className="space-y-4">
                {/* Overdue */}
                {deadlines.overdue.length > 0 && (
                  <DeadlineSection
                    title="Überfällig"
                    deadlines={deadlines.overdue}
                    variant="danger"
                  />
                )}

                {/* Today */}
                {deadlines.today.length > 0 && (
                  <DeadlineSection
                    title="Heute"
                    deadlines={deadlines.today}
                    variant="warning"
                  />
                )}

                {/* This Week */}
                {deadlines.thisWeek.length > 0 && (
                  <DeadlineSection
                    title="Diese Woche"
                    deadlines={deadlines.thisWeek}
                  />
                )}

                {/* This Month */}
                {deadlines.thisMonth.length > 0 && (
                  <DeadlineSection
                    title="Diesen Monat"
                    deadlines={deadlines.thisMonth.slice(0, 3)}
                  />
                )}

                {deadlines.overdue.length === 0 &&
                  deadlines.today.length === 0 &&
                  deadlines.thisWeek.length === 0 &&
                  deadlines.thisMonth.length === 0 && (
                    <p className="text-center py-4 text-muted-foreground text-sm">
                      Keine anstehenden Fristen
                    </p>
                  )}
              </div>
            ) : (
              <p className="text-center py-4 text-muted-foreground text-sm">
                Keine Fristendaten
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Enterprise Intelligence Section */}
      {spaceId && (
        <div className="space-y-6">
          {/* Financial Health & Net Worth Row */}
          <div className="grid gap-6 lg:grid-cols-2">
            <FinancialHealthDashboard spaceId={spaceId} compact />
            <NetWorthChart spaceId={spaceId} compact />
          </div>

          {/* Recommendations */}
          <RecommendationsPanel
            spaceId={spaceId}
            maxItems={5}
            showFilters={false}
          />
        </div>
      )}

      {/* Quick Links */}
      <div className="grid gap-4 md:grid-cols-4">
        <QuickLinkCard
          title="Immobilien"
          description="Grundstücke, Wohnungen & Mieter"
          icon={<Home className="h-6 w-6" />}
          link={buildLink('/privat/immobilien')}
          color="green"
        />
        <QuickLinkCard
          title="Fahrzeuge"
          description="Autos, Motorräder & Tankbelege"
          icon={<Car className="h-6 w-6" />}
          link={buildLink('/privat/fahrzeuge')}
          color="orange"
        />
        <QuickLinkCard
          title="Versicherungen"
          description="Alle Policen & Fristen"
          icon={<Shield className="h-6 w-6" />}
          link={buildLink('/privat/versicherungen')}
          color="red"
        />
        <QuickLinkCard
          title="Finanzen"
          description="Kredite & Geldanlagen"
          icon={<TrendingUp className="h-6 w-6" />}
          link={buildLink('/privat/finanzen')}
          color="blue"
        />
      </div>
    </div>
  );
}

interface StatCardProps {
  title: string;
  value: number;
  icon: React.ReactNode;
  link?: string;
  isLoading?: boolean;
}

function StatCard({ title, value, icon, link, isLoading }: StatCardProps) {
  const content = (
    <Card className={cn('hover:shadow-md transition-shadow', link && 'cursor-pointer')}>
      <CardContent className="flex items-center justify-between p-6">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          {isLoading ? (
            <Skeleton className="h-8 w-16 mt-1" />
          ) : (
            <p className="text-2xl font-bold">{value}</p>
          )}
        </div>
        <div className="p-2 rounded-lg bg-muted">{icon}</div>
      </CardContent>
    </Card>
  );

  if (link) {
    return <Link to={link}>{content}</Link>;
  }

  return content;
}

interface FinancialItemProps {
  label: string;
  value: string;
  positive?: boolean;
  large?: boolean;
}

function FinancialItem({ label, value, positive, large }: FinancialItemProps) {
  return (
    <div className={cn('p-4 rounded-lg bg-muted/50', large && 'md:col-span-2')}>
      <p className="text-sm text-muted-foreground mb-1">{label}</p>
      <p
        className={cn(
          'font-bold',
          large ? 'text-2xl' : 'text-lg',
          positive === true && 'text-green-600 dark:text-green-400',
          positive === false && 'text-red-600 dark:text-red-400'
        )}
      >
        {value}
      </p>
    </div>
  );
}

interface DeadlineSectionProps {
  title: string;
  deadlines: PrivatDeadlineWithStatus[];
  variant?: 'default' | 'warning' | 'danger';
}

function DeadlineSection({ title, deadlines, variant = 'default' }: DeadlineSectionProps) {
  return (
    <div>
      <h4
        className={cn(
          'text-sm font-medium mb-2',
          variant === 'danger' && 'text-red-600 dark:text-red-400',
          variant === 'warning' && 'text-amber-600 dark:text-amber-400'
        )}
      >
        {variant === 'danger' && <AlertTriangle className="inline h-3 w-3 mr-1" />}
        {title}
      </h4>
      <div className="space-y-2">
        {deadlines.map((deadline) => (
          <div
            key={deadline.id}
            className={cn(
              'flex items-center justify-between p-2 rounded-md text-sm',
              variant === 'danger' && 'bg-red-50 dark:bg-red-950/30',
              variant === 'warning' && 'bg-amber-50 dark:bg-amber-950/30',
              variant === 'default' && 'bg-muted/50'
            )}
          >
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <span className="truncate max-w-[150px]">{deadline.title}</span>
            </div>
            <span className="text-muted-foreground">{formatDate(deadline.dueDate)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

interface QuickLinkCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  link: string;
  color: 'green' | 'orange' | 'red' | 'blue';
}

function QuickLinkCard({ title, description, icon, link, color }: QuickLinkCardProps) {
  const colorClasses = {
    green: 'bg-green-100 dark:bg-green-950 text-green-600 dark:text-green-400',
    orange: 'bg-orange-100 dark:bg-orange-950 text-orange-600 dark:text-orange-400',
    red: 'bg-red-100 dark:bg-red-950 text-red-600 dark:text-red-400',
    blue: 'bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-400',
  };

  return (
    <Link to={link}>
      <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
        <CardContent className="p-4">
          <div className={cn('p-3 rounded-lg w-fit mb-3', colorClasses[color])}>
            {icon}
          </div>
          <h3 className="font-medium mb-1">{title}</h3>
          <p className="text-sm text-muted-foreground">{description}</p>
        </CardContent>
      </Card>
    </Link>
  );
}

export default PrivatDashboard;
