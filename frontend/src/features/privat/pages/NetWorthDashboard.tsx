/**
 * NetWorthDashboard - Nettovermögen-Dashboard
 *
 * Umfassendes Dashboard für die persönliche Vermögensposition:
 * - Zusammenfassungskarten (Vermögen, Verbindlichkeiten, Netto, Veränderung)
 * - Vermögensaufstellung nach Kategorien
 * - Verbindlichkeiten-Aufstellung
 * - Charts: Allokation, Verlauf, Vergleich
 * - Quick Actions
 */

import * as React from 'react';
import { logger } from '@/lib/logger';
import { Link } from '@tanstack/react-router';
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  Minus,
  ArrowUp,
  ArrowDown,
  RefreshCw,
  Plus,
  FileText,
  Target,
  RotateCcw,
  Download,
  AlertCircle,
  Home,
  Car,
  PiggyBank,
} from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { useSpaces, useCreatePortfolioSnapshot } from '../hooks/use-privat-queries';
import {
  useNetWorth,
  useRefreshNetWorth,
  formatCurrencyDE,
  formatPercentDE,
} from '../hooks/useNetWorth';
import {
  AssetBreakdownCard,
  LiabilityBreakdownCard,
  NetWorthLineChartCard as NetWorthChart,
  AllocationPieChart,
  ValuationUpdateDialog,
} from '../components/networth';

// ==================== Types ====================

interface SummaryCardProps {
  title: string;
  value: number;
  icon: React.ReactNode;
  trend?: number;
  trendLabel?: string;
  variant?: 'default' | 'success' | 'danger' | 'info';
  isLoading?: boolean;
}

// ==================== Summary Card ====================

function SummaryCard({
  title,
  value,
  icon,
  trend,
  trendLabel,
  variant = 'default',
  isLoading = false,
}: SummaryCardProps) {
  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-8 w-8 rounded-full" />
          </div>
          <Skeleton className="h-8 w-32 mt-2" />
          <Skeleton className="h-3 w-20 mt-2" />
        </CardContent>
      </Card>
    );
  }

  const variantStyles = {
    default: 'bg-card',
    success: 'bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800',
    danger: 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800',
    info: 'bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800',
  };

  const valueStyles = {
    default: 'text-foreground',
    success: 'text-green-600 dark:text-green-400',
    danger: 'text-red-600 dark:text-red-400',
    info: 'text-blue-600 dark:text-blue-400',
  };

  const trendIsPositive = trend !== undefined && trend >= 0;
  const trendIsNegative = trend !== undefined && trend < 0;

  return (
    <Card className={cn(variantStyles[variant])}>
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-muted-foreground">
            {title}
          </span>
          <div
            className={cn(
              'p-2 rounded-full',
              variant === 'default' && 'bg-muted',
              variant === 'success' && 'bg-green-100 dark:bg-green-900',
              variant === 'danger' && 'bg-red-100 dark:bg-red-900',
              variant === 'info' && 'bg-blue-100 dark:bg-blue-900'
            )}
          >
            {icon}
          </div>
        </div>

        <div className="mt-2">
          <span className={cn('text-2xl font-bold', valueStyles[variant])}>
            {formatCurrencyDE(value)}
          </span>
        </div>

        {trend !== undefined && (
          <div className="mt-2 flex items-center gap-1">
            {trendIsPositive && (
              <ArrowUp className="h-3 w-3 text-green-500" />
            )}
            {trendIsNegative && (
              <ArrowDown className="h-3 w-3 text-red-500" />
            )}
            {trend === 0 && (
              <Minus className="h-3 w-3 text-muted-foreground" />
            )}
            <span
              className={cn(
                'text-xs font-medium',
                trendIsPositive && 'text-green-600 dark:text-green-400',
                trendIsNegative && 'text-red-600 dark:text-red-400',
                trend === 0 && 'text-muted-foreground'
              )}
            >
              {trend > 0 ? '+' : ''}{formatPercentDE(trend)}
            </span>
            {trendLabel && (
              <span className="text-xs text-muted-foreground ml-1">
                {trendLabel}
              </span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ==================== Quick Actions ====================

function QuickActions({
  spaceId: _spaceId,
  onRefresh,
  isRefreshing,
  onValuationUpdate,
}: {
  spaceId: string;
  onRefresh: () => void;
  isRefreshing: boolean;
  onValuationUpdate: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button
        variant="outline"
        size="sm"
        onClick={onRefresh}
        disabled={isRefreshing}
      >
        <RefreshCw
          className={cn('h-4 w-4 mr-2', isRefreshing && 'animate-spin')}
        />
        {isRefreshing ? 'Aktualisiere...' : 'Aktualisieren'}
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm">
            <Plus className="h-4 w-4 mr-2" />
            Hinzufügen
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem asChild>
            <Link to="/privat/immobilien">
              <Home className="h-4 w-4 mr-2" />
              Immobilie
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link to="/privat/fahrzeuge">
              <Car className="h-4 w-4 mr-2" />
              Fahrzeug
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link to="/privat/finanzen">
              <PiggyBank className="h-4 w-4 mr-2" />
              Anlage
            </Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem asChild>
            <Link to="/privat/finanzen">
              <TrendingDown className="h-4 w-4 mr-2" />
              Kredit
            </Link>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm">
            <FileText className="h-4 w-4 mr-2" />
            Aktionen
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem asChild>
            <Link to="/privat/portfolio">
              <Target className="h-4 w-4 mr-2" />
              Finanzziel setzen
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onValuationUpdate}>
            <RotateCcw className="h-4 w-4 mr-2" />
            Bewertung aktualisieren
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => window.print()}>
            <Download className="h-4 w-4 mr-2" />
            Als PDF exportieren
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

// ==================== Loading State ====================

function DashboardSkeleton() {
  return (
    <div className="space-y-6 p-8">
      {/* Header Skeleton */}
      <div>
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-4 w-96 mt-2" />
      </div>

      {/* Summary Cards Skeleton */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardContent className="p-6">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-32 mt-2" />
              <Skeleton className="h-3 w-20 mt-2" />
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Charts Skeleton */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-40" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-64" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-40" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-64" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ==================== Main Component ====================

export function NetWorthDashboard() {
  // Get the first available space
  const { data: spaces = [], isLoading: spacesLoading } = useSpaces();
  const selectedSpaceId = spaces[0]?.id;

  // Fetch net worth data
  const {
    summary,
    history,
    isLoading: dataLoading,
    isFetching,
    error,
    refetch,
  } = useNetWorth(selectedSpaceId ?? '', {
    enabled: !!selectedSpaceId,
  });

  // Snapshot creation mutation
  const createSnapshotMutation = useCreatePortfolioSnapshot();
  void useRefreshNetWorth();

  // Handle refresh
  const handleRefresh = React.useCallback(async () => {
    if (!selectedSpaceId) return;
    try {
      await createSnapshotMutation.mutateAsync(selectedSpaceId);
      await refetch();
    } catch (err) {
      logger.error('Fehler beim Aktualisieren:', err);
    }
  }, [selectedSpaceId, createSnapshotMutation, refetch]);

  // Handle category click from pie chart
  const handleCategoryClick = React.useCallback((category: string) => {
    const routes: Record<string, string> = {
      properties: '/privat/immobilien',
      vehicles: '/privat/fahrzeuge',
      investments: '/privat/finanzen',
      bankAccounts: '/privat/finanzen',
      other: '/privat',
    };
    const route = routes[category];
    if (route) {
      window.location.href = route;
    }
  }, []);

  // Valuation dialog state
  const [valuationDialogOpen, setValuationDialogOpen] = React.useState(false);

  // Loading state
  const isLoading = spacesLoading || dataLoading;
  const isRefreshing = isFetching || createSnapshotMutation.isPending;

  // No space available
  if (!spacesLoading && spaces.length === 0) {
    return (
      <div className="flex items-center justify-center h-96 p-8">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Wallet className="h-5 w-5" />
              Kein Bereich vorhanden
            </CardTitle>
            <CardDescription>
              Erstellen Sie zuerst einen Privat-Bereich, um das
              Nettovermögen-Dashboard zu nutzen.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/privat">
              <Button>Bereich erstellen</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Loading state
  if (isLoading) {
    return <DashboardSkeleton />;
  }

  // Error state
  if (error) {
    return (
      <div className="p-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Fehler beim Laden</AlertTitle>
          <AlertDescription>
            Das Nettovermögen-Dashboard konnte nicht geladen werden. Bitte
            versuchen Sie es erneut.
            <Button
              variant="outline"
              size="sm"
              className="ml-4"
              onClick={() => refetch()}
            >
              Erneut versuchen
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  // Get summary data with defaults
  const totalAssets = summary?.totalAssets ?? 0;
  const totalLiabilities = summary?.totalLiabilities ?? 0;
  const netWorth = summary?.netWorth ?? 0;
  const monthlyChange = summary?.monthlyChange ?? 0;
  const monthlyChangePercent = summary?.monthlyChangePercent ?? 0;
  const assetBreakdown = summary?.assetBreakdown ?? [];
  const liabilityBreakdown = summary?.liabilityBreakdown ?? [];

  return (
    <div className="space-y-6 p-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Wallet className="h-8 w-8" />
            Nettovermögen
          </h1>
          <p className="text-muted-foreground mt-1">
            Ihre persönliche Vermögensposition im Überblick
          </p>
          {summary?.lastUpdated && (
            <p className="text-xs text-muted-foreground mt-1">
              Zuletzt aktualisiert:{' '}
              {new Date(summary.lastUpdated).toLocaleString('de-DE')}
            </p>
          )}
        </div>

        <QuickActions
          spaceId={selectedSpaceId!}
          onRefresh={handleRefresh}
          isRefreshing={isRefreshing}
          onValuationUpdate={() => setValuationDialogOpen(true)}
        />
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          title="Vermögen"
          value={totalAssets}
          icon={<TrendingUp className="h-4 w-4 text-green-500" />}
          variant="success"
        />
        <SummaryCard
          title="Verbindlichkeiten"
          value={totalLiabilities}
          icon={<TrendingDown className="h-4 w-4 text-red-500" />}
          variant="danger"
        />
        <SummaryCard
          title="Nettovermögen"
          value={netWorth}
          icon={<Wallet className="h-4 w-4 text-blue-500" />}
          variant={netWorth >= 0 ? 'info' : 'danger'}
        />
        <SummaryCard
          title="Monatliche Veränderung"
          value={monthlyChange}
          icon={
            monthlyChange >= 0 ? (
              <ArrowUp className="h-4 w-4 text-green-500" />
            ) : (
              <ArrowDown className="h-4 w-4 text-red-500" />
            )
          }
          trend={monthlyChangePercent}
          trendLabel="vs. Vormonat"
          variant={monthlyChange >= 0 ? 'success' : 'danger'}
        />
      </div>

      {/* Charts Row */}
      <div className="grid gap-4 md:grid-cols-2">
        <AllocationPieChart
          assets={assetBreakdown}
          totalAssets={totalAssets}
          onCategoryClick={handleCategoryClick}
        />
        <NetWorthChart history={history} />
      </div>

      {/* Breakdown Cards */}
      <div className="grid gap-4 md:grid-cols-2">
        <AssetBreakdownCard
          assets={assetBreakdown}
          totalAssets={totalAssets}
        />
        <LiabilityBreakdownCard
          liabilities={liabilityBreakdown}
          totalLiabilities={totalLiabilities}
        />
      </div>

      {/* Valuation Update Dialog */}
      {selectedSpaceId && (
        <ValuationUpdateDialog
          open={valuationDialogOpen}
          onOpenChange={setValuationDialogOpen}
          assets={assetBreakdown}
          spaceId={selectedSpaceId}
          onSuccess={handleRefresh}
        />
      )}
    </div>
  );
}

export default NetWorthDashboard;
