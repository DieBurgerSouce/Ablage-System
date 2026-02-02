/**
 * LiabilityBreakdownCard - Verbindlichkeiten-Aufstellung
 *
 * Zeigt die Aufschluesselung der Verbindlichkeiten nach Kategorien:
 * - Hypotheken
 * - Kredite
 * - Kreditkarten
 * - Sonstige
 */

import * as React from 'react';
import { Link } from '@tanstack/react-router';
import {
  Building,
  CreditCard,
  Landmark,
  Package,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  TrendingDown,
} from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import type { LiabilityBreakdown } from '../../hooks/useNetWorth';
import { formatCurrencyDE, formatPercentDE } from '../../hooks/useNetWorth';

// ==================== Types ====================

interface LiabilityBreakdownCardProps {
  liabilities: LiabilityBreakdown[];
  totalLiabilities: number;
  isLoading?: boolean;
  className?: string;
}

// ==================== Icon Map ====================

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  mortgages: <Building className="h-4 w-4" />,
  loans: <Landmark className="h-4 w-4" />,
  creditCards: <CreditCard className="h-4 w-4" />,
  other: <Package className="h-4 w-4" />,
};

// ==================== Loading Skeleton ====================

function LoadingSkeleton() {
  return (
    <Card>
      <CardHeader>
        <div className="h-5 w-40 bg-muted animate-pulse rounded" />
        <div className="h-4 w-56 bg-muted animate-pulse rounded mt-1" />
      </CardHeader>
      <CardContent className="space-y-4">
        {[1, 2].map((i) => (
          <div key={i} className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="h-4 w-24 bg-muted animate-pulse rounded" />
              <div className="h-4 w-20 bg-muted animate-pulse rounded" />
            </div>
            <div className="h-2 w-full bg-muted animate-pulse rounded" />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// ==================== Liability Category Row ====================

interface LiabilityCategoryRowProps {
  liability: LiabilityBreakdown;
  showItems?: boolean;
}

function LiabilityCategoryRow({ liability, showItems = false }: LiabilityCategoryRowProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const hasItems = liability.items.length > 0;

  // Calculate total monthly payments for this category
  const totalMonthlyPayment = liability.items.reduce(
    (sum, item) => sum + (item.monthlyPayment ?? 0),
    0
  );

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="space-y-2">
        {/* Main Row */}
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded-lg"
            style={{ backgroundColor: `${liability.color}20` }}
          >
            <span style={{ color: liability.color }}>
              {CATEGORY_ICONS[liability.category] ?? <Package className="h-4 w-4" />}
            </span>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm">{liability.label}</span>
                <span className="text-xs text-muted-foreground">
                  ({liability.count}x)
                </span>
              </div>
              <span className="font-semibold text-sm text-red-600 dark:text-red-400">
                -{formatCurrencyDE(liability.value)}
              </span>
            </div>

            <div className="flex items-center gap-2 mt-1">
              <Progress
                value={liability.percentage}
                className="h-2 flex-1"
                indicatorClassName={cn(
                  liability.category === 'mortgages' && 'bg-red-500',
                  liability.category === 'loans' && 'bg-orange-500',
                  liability.category === 'creditCards' && 'bg-pink-500',
                  liability.category === 'other' && 'bg-gray-500'
                )}
              />
              <span className="text-xs text-muted-foreground w-12 text-right">
                {formatPercentDE(liability.percentage)}
              </span>
            </div>

            {/* Monthly Payment Summary */}
            {totalMonthlyPayment > 0 && (
              <p className="text-xs text-muted-foreground mt-1">
                Monatliche Rate: {formatCurrencyDE(totalMonthlyPayment)}
              </p>
            )}
          </div>

          {/* Expand/Collapse Button */}
          {showItems && hasItems && (
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                {isOpen ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
                <span className="sr-only">
                  {isOpen ? 'Einklappen' : 'Ausklappen'}
                </span>
              </Button>
            </CollapsibleTrigger>
          )}

          {/* Navigate to Finances */}
          {!showItems && (
            <Link to="/privat/finanzen">
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                <ChevronRight className="h-4 w-4" />
                <span className="sr-only">Zu Finanzen</span>
              </Button>
            </Link>
          )}
        </div>

        {/* Expanded Items */}
        {showItems && hasItems && (
          <CollapsibleContent>
            <div className="ml-10 mt-2 space-y-2 border-l-2 border-muted pl-4">
              {liability.items.map((item) => (
                <div
                  key={item.id}
                  className="flex flex-col sm:flex-row sm:items-center justify-between text-sm py-1 gap-1"
                >
                  <span className="text-muted-foreground truncate max-w-[200px]">
                    {item.name}
                  </span>
                  <div className="flex items-center gap-4">
                    {item.monthlyPayment && item.monthlyPayment > 0 && (
                      <span className="text-xs text-muted-foreground">
                        {formatCurrencyDE(item.monthlyPayment)}/Monat
                      </span>
                    )}
                    <span className="font-medium text-red-600 dark:text-red-400">
                      -{formatCurrencyDE(item.outstanding)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CollapsibleContent>
        )}
      </div>
    </Collapsible>
  );
}

// ==================== Main Component ====================

export function LiabilityBreakdownCard({
  liabilities,
  totalLiabilities,
  isLoading = false,
  className,
}: LiabilityBreakdownCardProps) {
  const [showDetails, setShowDetails] = React.useState(false);

  // Calculate total monthly payments across all liabilities
  const totalMonthlyPayments = liabilities.reduce(
    (sum, liability) =>
      sum + liability.items.reduce((itemSum, item) => itemSum + (item.monthlyPayment ?? 0), 0),
    0
  );

  if (isLoading) {
    return <LoadingSkeleton />;
  }

  if (liabilities.length === 0 || totalLiabilities === 0) {
    return (
      <Card className={cn('', className)}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingDown className="h-5 w-5 text-red-500" />
            Verbindlichkeiten
          </CardTitle>
          <CardDescription>Keine Verbindlichkeiten erfasst</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="p-4 rounded-lg bg-green-50 dark:bg-green-950/30 text-center">
            <p className="text-green-600 dark:text-green-400 font-medium">
              Schuldenfrei
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Keine Kredite oder Hypotheken erfasst
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn('', className)}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <TrendingDown className="h-5 w-5 text-red-500" />
              Verbindlichkeiten
            </CardTitle>
            <CardDescription>
              Gesamt: -{formatCurrencyDE(totalLiabilities)}
            </CardDescription>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowDetails(!showDetails)}
          >
            {showDetails ? 'Weniger' : 'Details'}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {liabilities.map((liability) => (
          <LiabilityCategoryRow
            key={liability.category}
            liability={liability}
            showItems={showDetails}
          />
        ))}

        {/* Total Monthly Payments Summary */}
        {totalMonthlyPayments > 0 && (
          <div className="pt-4 border-t">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                Monatliche Gesamtbelastung
              </span>
              <span className="font-semibold text-red-600 dark:text-red-400">
                {formatCurrencyDE(totalMonthlyPayments)}
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default LiabilityBreakdownCard;
