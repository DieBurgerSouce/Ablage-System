/**
 * Supplier Ranking Table Component
 *
 * Tabelle mit allen Lieferanten und ihren Rankings.
 */

import { useState } from 'react';
import { Link } from '@tanstack/react-router';
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  TrendingUp,
  TrendingDown,
  Minus,
  Package,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Skeleton } from '@/components/ui/skeleton';
import { Checkbox } from '@/components/ui/checkbox';
import { TierBadge, ScoreBadge } from './SupplierScoreCard';
import { RankingFactors } from './RankingFactors';
import type { SupplierRanking } from '../types/supplier-ranking-types';
import { UI_LABELS, TIER_COLORS } from '../types/supplier-ranking-types';

interface SupplierRankingTableProps {
  suppliers: SupplierRanking[];
  isLoading?: boolean;
  selectable?: boolean;
  selectedIds?: string[];
  onSelectionChange?: (ids: string[]) => void;
  compact?: boolean;
  className?: string;
}

export function SupplierRankingTable({
  suppliers,
  isLoading = false,
  selectable = false,
  selectedIds = [],
  onSelectionChange,
  compact = false,
  className,
}: SupplierRankingTableProps) {
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className={cn('space-y-3', className)}>
        {[...Array(5)].map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (suppliers.length === 0) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center py-12 text-center',
          className
        )}
      >
        <Package className="h-12 w-12 text-muted-foreground/50 mb-4" />
        <h3 className="text-lg font-medium">{UI_LABELS.noSuppliers}</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Keine Lieferanten mit Ranking gefunden.
        </p>
      </div>
    );
  }

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      onSelectionChange?.(suppliers.map((s) => s.entityId));
    } else {
      onSelectionChange?.([]);
    }
  };

  const handleSelectOne = (entityId: string, checked: boolean) => {
    if (checked) {
      onSelectionChange?.([...selectedIds, entityId]);
    } else {
      onSelectionChange?.(selectedIds.filter((id) => id !== entityId));
    }
  };

  if (compact) {
    return (
      <div className={cn('space-y-2', className)}>
        {suppliers.map((supplier) => (
          <CompactSupplierRow
            key={supplier.entityId}
            supplier={supplier}
            selectable={selectable}
            selected={selectedIds.includes(supplier.entityId)}
            onSelect={(checked) => handleSelectOne(supplier.entityId, checked)}
          />
        ))}
      </div>
    );
  }

  return (
    <div className={cn('rounded-lg border', className)}>
      <Table>
        <TableHeader>
          <TableRow>
            {selectable && (
              <TableHead className="w-[40px]">
                <Checkbox
                  checked={selectedIds.length === suppliers.length && suppliers.length > 0}
                  onCheckedChange={handleSelectAll}
                />
              </TableHead>
            )}
            <TableHead className="w-[40px]" />
            <TableHead>{UI_LABELS.supplier}</TableHead>
            <TableHead>{UI_LABELS.tier}</TableHead>
            <TableHead className="text-right">{UI_LABELS.score}</TableHead>
            <TableHead className="text-right">{UI_LABELS.orders}</TableHead>
            <TableHead className="text-right">{UI_LABELS.volume}</TableHead>
            <TableHead>{UI_LABELS.trend}</TableHead>
            <TableHead className="text-right">Aktionen</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {suppliers.map((supplier) => (
            <SupplierTableRow
              key={supplier.entityId}
              supplier={supplier}
              expanded={expandedRow === supplier.entityId}
              onToggleExpand={() =>
                setExpandedRow(expandedRow === supplier.entityId ? null : supplier.entityId)
              }
              selectable={selectable}
              selected={selectedIds.includes(supplier.entityId)}
              onSelect={(checked) => handleSelectOne(supplier.entityId, checked)}
            />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/**
 * Single Supplier Table Row
 */
interface SupplierTableRowProps {
  supplier: SupplierRanking;
  expanded: boolean;
  onToggleExpand: () => void;
  selectable: boolean;
  selected: boolean;
  onSelect: (checked: boolean) => void;
}

function SupplierTableRow({
  supplier,
  expanded,
  onToggleExpand,
  selectable,
  selected,
  onSelect,
}: SupplierTableRowProps) {
  const tierColors = TIER_COLORS[supplier.tier];

  return (
    <Collapsible open={expanded} onOpenChange={onToggleExpand} asChild>
      <>
        <TableRow className={cn('cursor-pointer', expanded && 'bg-muted/50')}>
          {selectable && (
            <TableCell onClick={(e) => e.stopPropagation()}>
              <Checkbox
                checked={selected}
                onCheckedChange={onSelect}
              />
            </TableCell>
          )}
          <TableCell>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="icon" className="h-6 w-6">
                {expanded ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </Button>
            </CollapsibleTrigger>
          </TableCell>
          <TableCell>
            <div className="flex items-center gap-2">
              <span className="text-lg">{tierColors.icon}</span>
              <span className="font-medium">{supplier.entityName}</span>
            </div>
          </TableCell>
          <TableCell>
            <TierBadge tier={supplier.tier} showIcon={false} />
          </TableCell>
          <TableCell className="text-right">
            <ScoreBadge score={supplier.overallScore} tier={supplier.tier} size="sm" />
          </TableCell>
          <TableCell className="text-right font-medium">
            {supplier.totalOrders}
          </TableCell>
          <TableCell className="text-right">
            {formatCurrency(supplier.totalVolume)}
          </TableCell>
          <TableCell>
            <TrendIndicator trend={supplier.scoreTrend} showLabel />
          </TableCell>
          <TableCell className="text-right">
            <Button variant="ghost" size="icon" className="h-8 w-8" asChild>
              <Link to="/lieferanten/$supplierId" params={{ supplierId: supplier.entityId }}>
                <ExternalLink className="h-4 w-4" />
              </Link>
            </Button>
          </TableCell>
        </TableRow>
        <CollapsibleContent asChild>
          <TableRow className="bg-muted/30">
            <TableCell colSpan={selectable ? 10 : 9} className="p-4">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div>
                  <h4 className="text-sm font-medium mb-3">Kategorie-Scores</h4>
                  <RankingFactors categoryScores={supplier.categoryScores} showWeights />
                </div>
                <div>
                  <h4 className="text-sm font-medium mb-3">Details</h4>
                  <dl className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <dt className="text-muted-foreground">Gesamtscore</dt>
                      <dd className="font-bold text-lg">{supplier.overallScore.toFixed(1)}</dd>
                    </div>
                    {supplier.previousScore !== null && (
                      <div>
                        <dt className="text-muted-foreground">Vorheriger Score</dt>
                        <dd className="font-bold text-lg">{supplier.previousScore.toFixed(1)}</dd>
                      </div>
                    )}
                    <div>
                      <dt className="text-muted-foreground">Durchschn. Bestellwert</dt>
                      <dd className="font-medium">{formatCurrency(supplier.avgOrderValue)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Erste Bestellung</dt>
                      <dd className="font-medium">
                        {supplier.firstOrderDate
                          ? supplier.firstOrderDate.toLocaleDateString('de-DE')
                          : '-'}
                      </dd>
                    </div>
                  </dl>
                  {supplier.recommendations.length > 0 && (
                    <div className="mt-4 pt-4 border-t">
                      <h5 className="text-sm font-medium mb-2">Empfehlungen</h5>
                      <ul className="space-y-1 text-sm">
                        {supplier.recommendations.map((rec, idx) => (
                          <li key={idx}>• {rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            </TableCell>
          </TableRow>
        </CollapsibleContent>
      </>
    </Collapsible>
  );
}

/**
 * Compact Supplier Row (for mobile/sidebar)
 */
interface CompactSupplierRowProps {
  supplier: SupplierRanking;
  selectable: boolean;
  selected: boolean;
  onSelect: (checked: boolean) => void;
}

function CompactSupplierRow({
  supplier,
  selectable,
  selected,
  onSelect,
}: CompactSupplierRowProps) {
  const tierColors = TIER_COLORS[supplier.tier];

  return (
    <div
      className={cn(
        'flex items-center gap-3 p-3 rounded-lg border transition-colors hover:bg-accent/50',
        tierColors.bg
      )}
    >
      {selectable && (
        <Checkbox checked={selected} onCheckedChange={onSelect} />
      )}
      <span className="text-xl">{tierColors.icon}</span>
      <div className="flex-1 min-w-0">
        <p className="font-medium truncate">{supplier.entityName}</p>
        <div className="flex items-center gap-2 mt-1">
          <TierBadge tier={supplier.tier} showIcon={false} />
          <span className="text-xs text-muted-foreground">
            {supplier.totalOrders} Bestellungen
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <ScoreBadge score={supplier.overallScore} tier={supplier.tier} size="sm" />
        <Button variant="ghost" size="icon" className="h-8 w-8" asChild>
          <Link to="/lieferanten/$supplierId" params={{ supplierId: supplier.entityId }}>
            <ExternalLink className="h-4 w-4" />
          </Link>
        </Button>
      </div>
    </div>
  );
}

/**
 * Trend Indicator
 */
interface TrendIndicatorProps {
  trend: SupplierRanking['scoreTrend'];
  showLabel?: boolean;
}

function TrendIndicator({ trend, showLabel = false }: TrendIndicatorProps) {
  const config = {
    improving: {
      Icon: TrendingUp,
      color: 'text-green-600 dark:text-green-400',
      label: 'Besser',
    },
    declining: {
      Icon: TrendingDown,
      color: 'text-red-600 dark:text-red-400',
      label: 'Schlechter',
    },
    stable: {
      Icon: Minus,
      color: 'text-gray-500 dark:text-gray-400',
      label: 'Stabil',
    },
  };

  const { Icon, color, label } = config[trend];

  return (
    <span className={cn('inline-flex items-center gap-1', color)}>
      <Icon className="h-4 w-4" />
      {showLabel && <span className="text-xs">{label}</span>}
    </span>
  );
}

// Helper Functions
function formatCurrency(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M €`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K €`;
  }
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value);
}
