/**
 * InsuranceList - Versicherungs-Übersicht
 *
 * Liste aller Versicherungen mit Zahlungsfristen
 */

import * as React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
  Shield,
  Euro,
  Edit,
  Trash2,
  Eye,
  Search,
  ChevronLeft,
  ChevronRight,
  Calendar,
  AlertTriangle,
  RefreshCw,
  Filter,
} from 'lucide-react';
import type { PrivatInsuranceWithDeadlines, InsuranceType } from '@/types/privat';
import { cn } from '@/lib/utils';

interface InsuranceListProps {
  insurances: PrivatInsuranceWithDeadlines[];
  total: number;
  page: number;
  pageSize: number;
  isLoading?: boolean;
  error?: Error | null;
  onPageChange?: (page: number) => void;
  onSelect?: (insurance: PrivatInsuranceWithDeadlines) => void;
  onEdit?: (insurance: PrivatInsuranceWithDeadlines) => void;
  onDelete?: (insurance: PrivatInsuranceWithDeadlines) => void;
  onCreate?: () => void;
  onSearch?: (query: string) => void;
  onTypeFilter?: (type: InsuranceType | 'all') => void;
  selectedType?: InsuranceType | 'all';
  searchQuery?: string;
  className?: string;
}

const INSURANCE_TYPES: { value: InsuranceType | 'all'; label: string }[] = [
  { value: 'all', label: 'Alle Typen' },
  { value: 'health', label: 'Krankenversicherung' },
  { value: 'life', label: 'Lebensversicherung' },
  { value: 'liability', label: 'Haftpflicht' },
  { value: 'household', label: 'Hausrat' },
  { value: 'building', label: 'Gebäudeversicherung' },
  { value: 'vehicle', label: 'KFZ-Versicherung' },
  { value: 'legal', label: 'Rechtsschutz' },
  { value: 'disability', label: 'Berufsunfähigkeit' },
  { value: 'travel', label: 'Reiseversicherung' },
  { value: 'other', label: 'Sonstiges' },
];

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

const getInsuranceTypeLabel = (type: InsuranceType): string => {
  const found = INSURANCE_TYPES.find((t) => t.value === type);
  return found?.label || type;
};

const getInsuranceTypeColor = (type: InsuranceType): string => {
  const colors: Record<InsuranceType, string> = {
    health: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    life: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    liability: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    household: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
    building: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    vehicle: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
    legal: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
    disability: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200',
    travel: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200',
    other: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  };
  return colors[type];
};

const getPremiumIntervalLabel = (interval?: string): string => {
  if (!interval) return '';
  const intervals: Record<string, string> = {
    monthly: 'monatlich',
    quarterly: 'quartalsweise',
    semi_annual: 'halbjährlich',
    annual: 'jährlich',
  };
  return intervals[interval] || interval;
};

export function InsuranceList({
  insurances,
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
  onTypeFilter,
  selectedType = 'all',
  searchQuery = '',
  className,
}: InsuranceListProps) {
  const totalPages = Math.ceil(total / pageSize);

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Versicherungen</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Versicherungen
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
            <Shield className="h-6 w-6 text-red-600 dark:text-red-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Versicherungen</h1>
            <p className="text-muted-foreground">
              {total} {total === 1 ? 'Versicherung' : 'Versicherungen'}
            </p>
          </div>
        </div>
        {onCreate && (
          <Button onClick={onCreate}>
            <Plus className="mr-2 h-4 w-4" />
            Neue Versicherung
          </Button>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Suchen..."
            value={searchQuery}
            onChange={(e) => onSearch?.(e.target.value)}
            className="pl-8"
          />
        </div>
        <Select
          value={selectedType}
          onValueChange={(v) => onTypeFilter?.(v as InsuranceType | 'all')}
        >
          <SelectTrigger className="w-[200px]">
            <Filter className="mr-2 h-4 w-4" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {INSURANCE_TYPES.map((type) => (
              <SelectItem key={type.value} value={type.value}>
                {type.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      ) : insurances.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Shield className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">Keine Versicherungen</h3>
            <p className="text-muted-foreground text-center mb-4">
              Erfassen Sie Ihre Versicherungen, um Fristen und Kosten im Blick zu behalten.
            </p>
            {onCreate && (
              <Button onClick={onCreate}>
                <Plus className="mr-2 h-4 w-4" />
                Versicherung hinzufügen
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {insurances.map((insurance) => (
              <InsuranceCard
                key={insurance.id}
                insurance={insurance}
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

interface InsuranceCardProps {
  insurance: PrivatInsuranceWithDeadlines;
  onSelect?: (insurance: PrivatInsuranceWithDeadlines) => void;
  onEdit?: (insurance: PrivatInsuranceWithDeadlines) => void;
  onDelete?: (insurance: PrivatInsuranceWithDeadlines) => void;
}

function InsuranceCard({ insurance, onSelect, onEdit, onDelete }: InsuranceCardProps) {
  const isPaymentSoon = insurance.daysUntilPayment !== undefined && insurance.daysUntilPayment <= 7;
  const isPaymentOverdue = insurance.daysUntilPayment !== undefined && insurance.daysUntilPayment < 0;

  return (
    <Card
      className={cn(
        'hover:shadow-md transition-shadow',
        onSelect && 'cursor-pointer',
        isPaymentOverdue && 'border-red-500/50'
      )}
      onClick={() => onSelect?.(insurance)}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Badge
                variant="secondary"
                className={getInsuranceTypeColor(insurance.insuranceType)}
              >
                {getInsuranceTypeLabel(insurance.insuranceType)}
              </Badge>
              {insurance.autoRenewal && (
                <Badge variant="outline" className="text-xs">
                  <RefreshCw className="h-3 w-3 mr-1" />
                  Auto
                </Badge>
              )}
            </div>
            <CardTitle className="text-lg">{insurance.name}</CardTitle>
            {insurance.provider && (
              <CardDescription>{insurance.provider}</CardDescription>
            )}
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onSelect?.(insurance)}>
                <Eye className="mr-2 h-4 w-4" />
                Details
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onEdit?.(insurance)}>
                <Edit className="mr-2 h-4 w-4" />
                Bearbeiten
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => onDelete?.(insurance)}
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
        {/* Payment Warning */}
        {(isPaymentSoon || isPaymentOverdue) && (
          <div
            className={cn(
              'flex items-center gap-2 p-2 rounded-md mb-3 text-sm',
              isPaymentOverdue
                ? 'bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200'
                : 'bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200'
            )}
          >
            <AlertTriangle className="h-4 w-4" />
            <span>
              {isPaymentOverdue
                ? 'Zahlung überfällig!'
                : `Zahlung in ${insurance.daysUntilPayment} Tagen`}
            </span>
          </div>
        )}

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-3">
          {/* Premium */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <Euro className="h-4 w-4 text-green-500" />
            <div>
              <p className="text-xs text-muted-foreground">Prämie</p>
              <p className="font-medium">
                {formatCurrency(insurance.premium)}
                {insurance.premiumInterval && (
                  <span className="text-xs text-muted-foreground ml-1">
                    / {getPremiumIntervalLabel(insurance.premiumInterval)}
                  </span>
                )}
              </p>
            </div>
          </div>

          {/* Annual Cost */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <Euro className="h-4 w-4 text-amber-500" />
            <div>
              <p className="text-xs text-muted-foreground">Jährlich</p>
              <p className="font-medium">{formatCurrency(insurance.annualCost)}</p>
            </div>
          </div>

          {/* Coverage */}
          {insurance.coverageAmount !== undefined && (
            <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
              <Shield className="h-4 w-4 text-blue-500" />
              <div>
                <p className="text-xs text-muted-foreground">Deckung</p>
                <p className="font-medium">{formatCurrency(insurance.coverageAmount)}</p>
              </div>
            </div>
          )}

          {/* Next Payment */}
          {insurance.upcomingPayment && (
            <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
              <Calendar className="h-4 w-4 text-purple-500" />
              <div>
                <p className="text-xs text-muted-foreground">Nächste Zahlung</p>
                <p className="font-medium">{formatDate(insurance.upcomingPayment)}</p>
              </div>
            </div>
          )}
        </div>

        {/* Policy Number */}
        {insurance.policyNumber && (
          <div className="mt-3 pt-3 border-t text-sm text-muted-foreground">
            Policennummer: <span className="font-mono">{insurance.policyNumber}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default InsuranceList;
