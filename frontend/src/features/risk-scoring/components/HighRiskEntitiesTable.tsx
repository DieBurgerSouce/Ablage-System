/**
 * High Risk Entities Table Component
 *
 * Tabelle mit Hoch-Risiko Entities und Aktionen.
 */

import { useState } from 'react';
import { Link } from '@tanstack/react-router';
import {
  RefreshCw,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Users,
  Package,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
import { RiskScoreBadge, RiskIndicator } from './RiskScoreGauge';
import { RiskFactorBreakdown } from './RiskFactorBreakdown';
import type { EntityRisk } from '../types/risk-types';
import { RISK_LEVEL_COLORS, UI_LABELS } from '../types/risk-types';

interface HighRiskEntitiesTableProps {
  entities: EntityRisk[];
  isLoading?: boolean;
  onRecalculate?: (entityId: string) => void;
  isRecalculating?: string | null;
  compact?: boolean;
  className?: string;
}

export function HighRiskEntitiesTable({
  entities,
  isLoading = false,
  onRecalculate,
  isRecalculating,
  compact = false,
  className,
}: HighRiskEntitiesTableProps) {
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

  if (entities.length === 0) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center py-12 text-center',
          className
        )}
      >
        <AlertTriangle className="h-12 w-12 text-muted-foreground/50 mb-4" />
        <h3 className="text-lg font-medium">Keine Hoch-Risiko Entities</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Es wurden keine Entities mit hohem Risiko gefunden.
        </p>
      </div>
    );
  }

  if (compact) {
    return (
      <div className={cn('space-y-2', className)}>
        {entities.map((entity) => (
          <div
            key={entity.entityId}
            className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors"
          >
            <div className="flex items-center gap-3 min-w-0">
              {entity.entityType === 'customer' ? (
                <Users className="h-4 w-4 text-muted-foreground flex-shrink-0" />
              ) : (
                <Package className="h-4 w-4 text-muted-foreground flex-shrink-0" />
              )}
              <div className="min-w-0">
                <p className="font-medium truncate">{entity.entityName}</p>
                <p className="text-xs text-muted-foreground">
                  {entity.entityType === 'customer' ? 'Kunde' : 'Lieferant'}
                </p>
              </div>
            </div>
            <RiskIndicator score={entity.riskScore} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={cn('rounded-lg border', className)}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[40px]" />
            <TableHead>{UI_LABELS.entity}</TableHead>
            <TableHead>{UI_LABELS.type}</TableHead>
            <TableHead className="text-right">{UI_LABELS.score}</TableHead>
            <TableHead>{UI_LABELS.lastCalculated}</TableHead>
            <TableHead className="text-right">Aktionen</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entities.map((entity) => (
            <Collapsible
              key={entity.entityId}
              open={expandedRow === entity.entityId}
              onOpenChange={(open) =>
                setExpandedRow(open ? entity.entityId : null)
              }
              asChild
            >
              <>
                <TableRow
                  className={cn(
                    'cursor-pointer',
                    expandedRow === entity.entityId && 'bg-muted/50'
                  )}
                >
                  <TableCell>
                    <CollapsibleTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-6 w-6">
                        {expandedRow === entity.entityId ? (
                          <ChevronUp className="h-4 w-4" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </Button>
                    </CollapsibleTrigger>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div
                        className={cn(
                          'w-2 h-2 rounded-full',
                          RISK_LEVEL_COLORS[entity.riskLevel].border
                        )}
                        style={{
                          backgroundColor:
                            entity.riskLevel === 'critical'
                              ? '#ef4444'
                              : entity.riskLevel === 'high'
                                ? '#f97316'
                                : entity.riskLevel === 'medium'
                                  ? '#eab308'
                                  : '#22c55e',
                        }}
                      />
                      <span className="font-medium">{entity.entityName}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="gap-1">
                      {entity.entityType === 'customer' ? (
                        <>
                          <Users className="h-3 w-3" />
                          Kunde
                        </>
                      ) : (
                        <>
                          <Package className="h-3 w-3" />
                          Lieferant
                        </>
                      )}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <RiskScoreBadge score={entity.riskScore} size="sm" />
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-muted-foreground">
                      {entity.calculatedAt.toLocaleDateString('de-DE', {
                        day: '2-digit',
                        month: '2-digit',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      {onRecalculate && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={(e) => {
                            e.stopPropagation();
                            onRecalculate(entity.entityId);
                          }}
                          disabled={isRecalculating === entity.entityId}
                        >
                          {isRecalculating === entity.entityId ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <RefreshCw className="h-4 w-4" />
                          )}
                        </Button>
                      )}
                      <Button variant="ghost" size="icon" className="h-8 w-8" asChild>
                        <Link
                          to={
                            entity.entityType === 'customer'
                              ? '/kunden/$entityId'
                              : '/lieferanten/$entityId'
                          }
                          params={{ entityId: entity.entityId }}
                        >
                          <ExternalLink className="h-4 w-4" />
                        </Link>
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
                <CollapsibleContent asChild>
                  <TableRow className="bg-muted/30">
                    <TableCell colSpan={6} className="p-4">
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div>
                          <h4 className="text-sm font-medium mb-3">
                            Risikofaktoren
                          </h4>
                          <RiskFactorBreakdown
                            factors={entity.riskFactors}
                            showWeights
                          />
                        </div>
                        <div>
                          <h4 className="text-sm font-medium mb-3">
                            Details
                          </h4>
                          <dl className="grid grid-cols-2 gap-4 text-sm">
                            <div>
                              <dt className="text-muted-foreground">Risiko-Score</dt>
                              <dd className="font-bold text-lg">{entity.riskScore.toFixed(1)}</dd>
                            </div>
                            {entity.paymentBehaviorScore !== null && (
                              <div>
                                <dt className="text-muted-foreground">Zahlungsverhalten</dt>
                                <dd className="font-bold text-lg">{entity.paymentBehaviorScore.toFixed(1)}</dd>
                              </div>
                            )}
                            <div>
                              <dt className="text-muted-foreground">Entity-Typ</dt>
                              <dd className="font-medium">
                                {entity.entityType === 'customer' ? 'Kunde' : 'Lieferant'}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">Letzte Berechnung</dt>
                              <dd className="font-medium">
                                {entity.calculatedAt.toLocaleString('de-DE')}
                              </dd>
                            </div>
                          </dl>
                        </div>
                      </div>
                    </TableCell>
                  </TableRow>
                </CollapsibleContent>
              </>
            </Collapsible>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/**
 * Simple Risk Entity List (for sidebar/widgets)
 */
interface RiskEntityListProps {
  entities: EntityRisk[];
  maxItems?: number;
  className?: string;
}

export function RiskEntityList({
  entities,
  maxItems = 5,
  className,
}: RiskEntityListProps) {
  const displayEntities = entities.slice(0, maxItems);

  return (
    <div className={cn('space-y-2', className)}>
      {displayEntities.map((entity) => (
        <Link
          key={entity.entityId}
          to={
            entity.entityType === 'customer'
              ? '/kunden/$entityId'
              : '/lieferanten/$entityId'
          }
          params={{ entityId: entity.entityId }}
          className="flex items-center justify-between p-2 rounded-md hover:bg-accent transition-colors"
        >
          <div className="flex items-center gap-2 min-w-0">
            {entity.entityType === 'customer' ? (
              <Users className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            ) : (
              <Package className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            )}
            <span className="text-sm truncate">{entity.entityName}</span>
          </div>
          <RiskIndicator score={entity.riskScore} />
        </Link>
      ))}
      {entities.length > maxItems && (
        <p className="text-xs text-center text-muted-foreground pt-2">
          +{entities.length - maxItems} weitere
        </p>
      )}
    </div>
  );
}
