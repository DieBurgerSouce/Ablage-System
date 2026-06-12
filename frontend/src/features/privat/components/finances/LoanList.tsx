/**
 * LoanList - Kredite-Übersicht
 *
 * Liste aller Kredite mit Tilgungsfortschritt
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
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
  CreditCard,
  Euro,
  Edit,
  Trash2,
  Eye,
  Search,
  ChevronLeft,
  ChevronRight,
  Calendar,
  TrendingDown,
  Percent,
} from 'lucide-react';
import type { PrivatLoanWithStats, LoanType } from '@/types/privat';
import { cn } from '@/lib/utils';

interface LoanListProps {
  loans: PrivatLoanWithStats[];
  total: number;
  page: number;
  pageSize: number;
  isLoading?: boolean;
  error?: Error | null;
  onPageChange?: (page: number) => void;
  onSelect?: (loan: PrivatLoanWithStats) => void;
  onEdit?: (loan: PrivatLoanWithStats) => void;
  onDelete?: (loan: PrivatLoanWithStats) => void;
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

const getLoanTypeLabel = (type: LoanType): string => {
  const types: Record<LoanType, string> = {
    mortgage: 'Hypothek',
    personal: 'Privatkredit',
    car: 'Autokredit',
    student: 'Studienkredit',
    business: 'Geschäftskredit',
    other: 'Sonstiges',
  };
  return types[type];
};

const getLoanTypeColor = (type: LoanType): string => {
  const colors: Record<LoanType, string> = {
    mortgage: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    personal: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    car: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
    student: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    business: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
    other: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  };
  return colors[type];
};

export function LoanList({
  loans,
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
}: LoanListProps) {
  const totalPages = Math.ceil(total / pageSize);

  // Calculate totals
  const totalBalance = loans.reduce((sum, l) => sum + l.currentBalance, 0);
  const totalMonthlyPayment = loans.reduce((sum, l) => sum + (l.monthlyPayment || 0), 0);

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Kredite</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Kredite
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
          <div className="p-2 rounded-lg bg-red-100 dark:bg-red-950">
            <CreditCard className="h-6 w-6 text-red-600 dark:text-red-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Kredite</h1>
            <p className="text-muted-foreground">
              {total} {total === 1 ? 'Kredit' : 'Kredite'}
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
              Neuer Kredit
            </Button>
          )}
        </div>
      </div>

      {/* Summary Cards */}
      {loans.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-sm text-muted-foreground">Gesamtschulden</p>
                <p className="text-2xl font-bold text-red-600 dark:text-red-400">
                  {formatCurrency(totalBalance)}
                </p>
              </div>
              <CreditCard className="h-8 w-8 text-red-500 opacity-50" />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-sm text-muted-foreground">Monatliche Raten</p>
                <p className="text-2xl font-bold">
                  {formatCurrency(totalMonthlyPayment)}
                </p>
              </div>
              <TrendingDown className="h-8 w-8 text-muted-foreground opacity-50" />
            </CardContent>
          </Card>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      ) : loans.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <CreditCard className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">Keine Kredite</h3>
            <p className="text-muted-foreground text-center mb-4">
              Erfassen Sie Ihre Kredite, um Tilgungsfortschritt und Zahlungen zu verfolgen.
            </p>
            {onCreate && (
              <Button onClick={onCreate}>
                <Plus className="mr-2 h-4 w-4" />
                Kredit hinzufügen
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {loans.map((loan) => (
              <LoanCard
                key={loan.id}
                loan={loan}
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

interface LoanCardProps {
  loan: PrivatLoanWithStats;
  onSelect?: (loan: PrivatLoanWithStats) => void;
  onEdit?: (loan: PrivatLoanWithStats) => void;
  onDelete?: (loan: PrivatLoanWithStats) => void;
}

function LoanCard({ loan, onSelect, onEdit, onDelete }: LoanCardProps) {
  const repaymentProgress =
    loan.principalAmount > 0
      ? ((loan.principalAmount - loan.currentBalance) / loan.principalAmount) * 100
      : 0;

  return (
    <Card
      className={cn(
        'hover:shadow-md transition-shadow',
        onSelect && 'cursor-pointer'
      )}
      onClick={() => onSelect?.(loan)}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <Badge
              variant="secondary"
              className={cn('mb-2', getLoanTypeColor(loan.loanType))}
            >
              {getLoanTypeLabel(loan.loanType)}
            </Badge>
            <CardTitle className="text-lg">{loan.name}</CardTitle>
            {loan.lender && <CardDescription>{loan.lender}</CardDescription>}
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onSelect?.(loan)}>
                <Eye className="mr-2 h-4 w-4" />
                Details
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onEdit?.(loan)}>
                <Edit className="mr-2 h-4 w-4" />
                Bearbeiten
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => onDelete?.(loan)}
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
        {/* Progress */}
        <div className="mb-4">
          <div className="flex items-center justify-between text-sm mb-2">
            <span className="text-muted-foreground">Tilgungsfortschritt</span>
            <span className="font-medium">{repaymentProgress.toFixed(1)}%</span>
          </div>
          <Progress value={repaymentProgress} className="h-2" />
          <div className="flex items-center justify-between text-xs text-muted-foreground mt-1">
            <span>Getilgt: {formatCurrency(loan.totalPaid)}</span>
            <span>Restschuld: {formatCurrency(loan.currentBalance)}</span>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-3">
          {/* Original Amount */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <Euro className="h-4 w-4 text-blue-500" />
            <div>
              <p className="text-xs text-muted-foreground">Ursprungsbetrag</p>
              <p className="font-medium">{formatCurrency(loan.principalAmount)}</p>
            </div>
          </div>

          {/* Monthly Payment */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <TrendingDown className="h-4 w-4 text-green-500" />
            <div>
              <p className="text-xs text-muted-foreground">Monatl. Rate</p>
              <p className="font-medium">{formatCurrency(loan.monthlyPayment)}</p>
            </div>
          </div>

          {/* Interest Rate */}
          {loan.interestRate !== undefined && (
            <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
              <Percent className="h-4 w-4 text-amber-500" />
              <div>
                <p className="text-xs text-muted-foreground">Zinssatz</p>
                <p className="font-medium">{loan.interestRate.toFixed(2)}%</p>
              </div>
            </div>
          )}

          {/* Remaining Months */}
          {loan.remainingMonths !== undefined && (
            <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
              <Calendar className="h-4 w-4 text-purple-500" />
              <div>
                <p className="text-xs text-muted-foreground">Restlaufzeit</p>
                <p className="font-medium">
                  {loan.remainingMonths} {loan.remainingMonths === 1 ? 'Monat' : 'Monate'}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Next Payment and Interest Paid */}
        <div className="mt-3 pt-3 border-t text-sm flex justify-between">
          {loan.nextPaymentDate && (
            <span className="text-muted-foreground">
              Nächste Rate: {formatDate(loan.nextPaymentDate)}
            </span>
          )}
          {loan.totalInterestPaid !== undefined && (
            <span className="text-muted-foreground">
              Zinsen bezahlt: {formatCurrency(loan.totalInterestPaid)}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default LoanList;
