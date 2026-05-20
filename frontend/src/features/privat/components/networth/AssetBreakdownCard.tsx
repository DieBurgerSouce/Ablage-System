/**
 * AssetBreakdownCard - Vermögensaufstellung
 *
 * Zeigt die Aufschlüsselung des Vermögens nach Kategorien:
 * - Immobilien
 * - Fahrzeuge
 * - Anlagen
 * - Bankkonten
 * - Sonstiges
 */

import * as React from 'react';
import { Link } from '@tanstack/react-router';
import {
  Home,
  Car,
  TrendingUp,
  Landmark,
  Package,
  ChevronRight,
  ChevronDown,
  ChevronUp,
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
import type { AssetBreakdown } from '../../hooks/useNetWorth';
import { formatCurrencyDE, formatPercentDE } from '../../hooks/useNetWorth';

// ==================== Types ====================

interface AssetBreakdownCardProps {
  assets: AssetBreakdown[];
  totalAssets: number;
  isLoading?: boolean;
  className?: string;
}

// ==================== Icon Map ====================

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  properties: <Home className="h-4 w-4" />,
  vehicles: <Car className="h-4 w-4" />,
  investments: <TrendingUp className="h-4 w-4" />,
  bankAccounts: <Landmark className="h-4 w-4" />,
  other: <Package className="h-4 w-4" />,
};

const CATEGORY_ROUTES: Record<string, string> = {
  properties: '/privat/immobilien',
  vehicles: '/privat/fahrzeuge',
  investments: '/privat/finanzen',
  bankAccounts: '/privat/finanzen',
  other: '/privat',
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
        {[1, 2, 3].map((i) => (
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

// ==================== Asset Category Row ====================

interface AssetCategoryRowProps {
  asset: AssetBreakdown;
  showItems?: boolean;
}

function AssetCategoryRow({ asset, showItems = false }: AssetCategoryRowProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const hasItems = asset.items.length > 0;

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="space-y-2">
        {/* Main Row */}
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded-lg"
            style={{ backgroundColor: `${asset.color}20` }}
          >
            <span style={{ color: asset.color }}>
              {CATEGORY_ICONS[asset.category] ?? <Package className="h-4 w-4" />}
            </span>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm">{asset.label}</span>
                <span className="text-xs text-muted-foreground">
                  ({asset.count}x)
                </span>
              </div>
              <span className="font-semibold text-sm">
                {formatCurrencyDE(asset.value)}
              </span>
            </div>

            <div className="flex items-center gap-2 mt-1">
              <Progress
                value={asset.percentage}
                className="h-2 flex-1"
                indicatorClassName={cn(
                  asset.category === 'properties' && 'bg-blue-500',
                  asset.category === 'vehicles' && 'bg-emerald-500',
                  asset.category === 'investments' && 'bg-amber-500',
                  asset.category === 'bankAccounts' && 'bg-green-500',
                  asset.category === 'other' && 'bg-violet-500'
                )}
              />
              <span className="text-xs text-muted-foreground w-12 text-right">
                {formatPercentDE(asset.percentage)}
              </span>
            </div>
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

          {/* Navigate to Category */}
          {!showItems && (
            <Link to={CATEGORY_ROUTES[asset.category] ?? '/privat'}>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                <ChevronRight className="h-4 w-4" />
                <span className="sr-only">Zu {asset.label}</span>
              </Button>
            </Link>
          )}
        </div>

        {/* Expanded Items */}
        {showItems && hasItems && (
          <CollapsibleContent>
            <div className="ml-10 mt-2 space-y-1 border-l-2 border-muted pl-4">
              {asset.items.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between text-sm py-1"
                >
                  <span className="text-muted-foreground truncate max-w-[200px]">
                    {item.name}
                  </span>
                  <span className="font-medium">
                    {formatCurrencyDE(item.value)}
                  </span>
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

export function AssetBreakdownCard({
  assets,
  totalAssets,
  isLoading = false,
  className,
}: AssetBreakdownCardProps) {
  const [showDetails, setShowDetails] = React.useState(false);

  if (isLoading) {
    return <LoadingSkeleton />;
  }

  if (assets.length === 0) {
    return (
      <Card className={cn('', className)}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-green-500" />
            Vermögensaufstellung
          </CardTitle>
          <CardDescription>Keine Vermögenswerte erfasst</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-center text-muted-foreground py-6">
            Erfassen Sie Ihre Immobilien, Fahrzeuge und Anlagen, um Ihre
            Vermögensposition zu sehen.
          </p>
          <div className="flex gap-2 justify-center">
            <Link to="/privat/immobilien">
              <Button variant="outline" size="sm">
                <Home className="h-4 w-4 mr-2" />
                Immobilie hinzufügen
              </Button>
            </Link>
            <Link to="/privat/finanzen">
              <Button variant="outline" size="sm">
                <TrendingUp className="h-4 w-4 mr-2" />
                Anlage hinzufügen
              </Button>
            </Link>
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
              <TrendingUp className="h-5 w-5 text-green-500" />
              Vermögensaufstellung
            </CardTitle>
            <CardDescription>
              Gesamt: {formatCurrencyDE(totalAssets)}
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
        {assets.map((asset) => (
          <AssetCategoryRow
            key={asset.category}
            asset={asset}
            showItems={showDetails}
          />
        ))}
      </CardContent>
    </Card>
  );
}

export default AssetBreakdownCard;
