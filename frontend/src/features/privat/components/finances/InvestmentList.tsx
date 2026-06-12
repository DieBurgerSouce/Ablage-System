/**
 * InvestmentList - Geldanlagen-Übersicht
 *
 * Liste aller Investments mit Renditeberechnung
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Plus,
  MoreHorizontal,
  TrendingUp,
  TrendingDown,
  Euro,
  Edit,
  Trash2,
  Eye,
  Search,
  ChevronLeft,
  ChevronRight,
  Calendar,
  Percent,
  PiggyBank,
} from 'lucide-react';
import type { PrivatInvestmentWithStats, InvestmentType } from '@/types/privat';
import { cn } from '@/lib/utils';

interface InvestmentListProps {
  investments: PrivatInvestmentWithStats[];
  total: number;
  page: number;
  pageSize: number;
  isLoading?: boolean;
  error?: Error | null;
  onPageChange?: (page: number) => void;
  onSelect?: (investment: PrivatInvestmentWithStats) => void;
  onEdit?: (investment: PrivatInvestmentWithStats) => void;
  onDelete?: (investment: PrivatInvestmentWithStats) => void;
  onCreate?: () => void;
  onSearch?: (query: string) => void;
  searchQuery?: string;
  className?: string;
}

const formatCurrency = (amount?: number): string => {
  if (amount === undefined) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
};

const formatDate = (dateStr?: string): string => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

const getInvestmentTypeLabel = (type: InvestmentType): string => {
  const types: Record<InvestmentType, string> = {
    savings: 'Sparkonto',
    stocks: 'Aktien',
    bonds: 'Anleihen',
    fund: 'Fonds',
    etf: 'ETF',
    real_estate: 'Immobilienfonds',
    crypto: 'Krypto',
    pension: 'Rente',
    other: 'Sonstiges',
  };
  return types[type];
};

const getInvestmentTypeColor = (type: InvestmentType): string => {
  const colors: Record<InvestmentType, string> = {
    savings: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    stocks: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    bonds: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
    fund: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    etf: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
    real_estate: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
    crypto: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200',
    pension: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200',
    other: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  };
  return colors[type];
};

export function InvestmentList({
  investments,
  total,
  page,
  pageSize,
  isLoading,
  error,
  onPageChange,
  onSelect,
  onEdit,
  onDelete,
  onCreate,
  onSearch,
  searchQuery = '',
  className,
}: InvestmentListProps) {
  const totalPages = Math.ceil(total / pageSize);

  // Calculate totals
  const totalValue = investments.reduce((sum, i) => sum + i.currentValue, 0);
  const totalInitial = investments.reduce((sum, i) => sum + i.initialAmount, 0);
  const totalReturn = totalValue - totalInitial;
  const totalReturnPercentage = totalInitial > 0 ? (totalReturn / totalInitial) * 100 : 0;

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Geldanlagen</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Geldanlagen
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-green-100 dark:bg-green-950">
            <TrendingUp className="h-6 w-6 text-green-600 dark:text-green-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Geldanlagen</h1>
            <p className="text-muted-foreground">
              {total} {total === 1 ? 'Anlage' : 'Anlagen'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Suchen..."
              value={searchQuery}
              onChange={(e) => onSearch?.(e.target.value)}
              className="pl-8 w-[200px]"
            />
          </div>
          {onCreate && (
            <Button onClick={onCreate}>
              <Plus className="mr-2 h-4 w-4" />
              Neue Anlage
            </Button>
          )}
        </div>
      </div>

      {/* Summary Cards */}
      {investments.length > 0 && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-sm text-muted-foreground">Gesamtwert</p>
                <p className="text-2xl font-bold">{formatCurrency(totalValue)}</p>
              </div>
              <PiggyBank className="h-8 w-8 text-green-500 opacity-50" />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-sm text-muted-foreground">Gewinn/Verlust</p>
                <p
                  className={cn(
                    'text-2xl font-bold',
                    totalReturn >= 0 ? 'text-green-600' : 'text-red-600'
                  )}
                >
                  {totalReturn >= 0 ? '+' : ''}
                  {formatCurrency(totalReturn)}
                </p>
              </div>
              {totalReturn >= 0 ? (
                <TrendingUp className="h-8 w-8 text-green-500 opacity-50" />
              ) : (
                <TrendingDown className="h-8 w-8 text-red-500 opacity-50" />
              )}
            </CardContent>
          </Card>
          <Card>
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-sm text-muted-foreground">Rendite</p>
                <p
                  className={cn(
                    'text-2xl font-bold',
                    totalReturnPercentage >= 0 ? 'text-green-600' : 'text-red-600'
                  )}
                >
                  {totalReturnPercentage >= 0 ? '+' : ''}
                  {totalReturnPercentage.toFixed(2)}%
                </p>
              </div>
              <Percent className="h-8 w-8 text-muted-foreground opacity-50" />
            </CardContent>
          </Card>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      ) : investments.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <TrendingUp className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">Keine Geldanlagen</h3>
            <p className="text-muted-foreground text-center mb-4">
              Erfassen Sie Ihre Geldanlagen, um Renditen und Entwicklung zu verfolgen.
            </p>
            {onCreate && (
              <Button onClick={onCreate}>
                <Plus className="mr-2 h-4 w-4" />
                Anlage hinzufügen
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {investments.map((investment) => (
              <InvestmentCard
                key={investment.id}
                investment={investment}
                onSelect={onSelect}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <div className="text-sm text-muted-foreground">
                Seite {page + 1} von {totalPages}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onPageChange?.(Math.max(0, page - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                  Zurück
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onPageChange?.(Math.min(totalPages - 1, page + 1))}
                  disabled={page >= totalPages - 1}
                >
                  Weiter
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

interface InvestmentCardProps {
  investment: PrivatInvestmentWithStats;
  onSelect?: (investment: PrivatInvestmentWithStats) => void;
  onEdit?: (investment: PrivatInvestmentWithStats) => void;
  onDelete?: (investment: PrivatInvestmentWithStats) => void;
}

function InvestmentCard({ investment, onSelect, onEdit, onDelete }: InvestmentCardProps) {
  const isPositive = investment.returnPercentage >= 0;

  return (
    <Card
      className={cn(
        'hover:shadow-md transition-shadow',
        onSelect && 'cursor-pointer'
      )}
      onClick={() => onSelect?.(investment)}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Badge
                variant="secondary"
                className={getInvestmentTypeColor(investment.investmentType)}
              >
                {getInvestmentTypeLabel(investment.investmentType)}
              </Badge>
              {investment.isTaxable && (
                <Badge variant="outline" className="text-xs">
                  Steuerpflichtig
                </Badge>
              )}
            </div>
            <CardTitle className="text-lg">{investment.name}</CardTitle>
            {investment.institution && (
              <CardDescription>{investment.institution}</CardDescription>
            )}
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onSelect?.(investment)}>
                <Eye className="mr-2 h-4 w-4" />
                Details
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onEdit?.(investment)}>
                <Edit className="mr-2 h-4 w-4" />
                Bearbeiten
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => onDelete?.(investment)}
                className="text-destructive"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Löschen
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardHeader>
      <CardContent>
        {/* Value and Return */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-2xl font-bold">{formatCurrency(investment.currentValue)}</p>
            <p className="text-sm text-muted-foreground">
              Investiert: {formatCurrency(investment.initialAmount)}
            </p>
          </div>
          <div className="text-right">
            <div
              className={cn(
                'flex items-center gap-1 text-lg font-semibold',
                isPositive ? 'text-green-600' : 'text-red-600'
              )}
            >
              {isPositive ? (
                <TrendingUp className="h-5 w-5" />
              ) : (
                <TrendingDown className="h-5 w-5" />
              )}
              <span>
                {isPositive ? '+' : ''}
                {investment.returnPercentage.toFixed(2)}%
              </span>
            </div>
            <p
              className={cn(
                'text-sm',
                isPositive ? 'text-green-600' : 'text-red-600'
              )}
            >
              {isPositive ? '+' : ''}
              {formatCurrency(investment.totalReturn)}
            </p>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-3">
          {/* Interest Rate */}
          {investment.interestRate !== undefined && (
            <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
              <Percent className="h-4 w-4 text-amber-500" />
              <div>
                <p className="text-xs text-muted-foreground">Zinssatz</p>
                <p className="font-medium">{investment.interestRate.toFixed(2)}%</p>
              </div>
            </div>
          )}

          {/* Annual Return */}
          {investment.annualReturn !== undefined && (
            <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
              <Euro className="h-4 w-4 text-green-500" />
              <div>
                <p className="text-xs text-muted-foreground">Jährl. Rendite</p>
                <p className="font-medium">{formatCurrency(investment.annualReturn)}</p>
              </div>
            </div>
          )}

          {/* Start Date */}
          {investment.startDate && (
            <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
              <Calendar className="h-4 w-4 text-blue-500" />
              <div>
                <p className="text-xs text-muted-foreground">Beginn</p>
                <p className="font-medium">{formatDate(investment.startDate)}</p>
              </div>
            </div>
          )}

          {/* Maturity Date */}
          {investment.maturityDate && (
            <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
              <Calendar className="h-4 w-4 text-purple-500" />
              <div>
                <p className="text-xs text-muted-foreground">Fälligkeit</p>
                <p className="font-medium">{formatDate(investment.maturityDate)}</p>
              </div>
            </div>
          )}
        </div>

        {/* Account Number */}
        {investment.accountNumber && (
          <div className="mt-3 pt-3 border-t text-sm text-muted-foreground">
            Kontonummer: <span className="font-mono">{investment.accountNumber}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default InvestmentList;
