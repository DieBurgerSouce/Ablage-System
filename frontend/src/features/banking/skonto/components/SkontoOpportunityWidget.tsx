/**
 * SkontoOpportunityWidget - Dashboard Widget für Skonto-Gelegenheiten
 *
 * Zeigt bevorstehende Skonto-Fristen im Dashboard.
 *
 * Features:
 * - Liste der Top-N Skonto-Gelegenheiten
 * - Sortiert nach Dringlichkeit
 * - Quick-Link zu Rechnungsdetails
 * - Gesamtsumme potentieller Ersparnisse
 */

import { useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import { TrendingDown, Clock, AlertTriangle, ArrowRight, Loader2 } from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useUpcomingSkonto } from '../hooks';
import { SKONTO_COLORS } from '../types';

interface SkontoOpportunityWidgetProps {
  daysAhead?: number;
  limit?: number;
  className?: string;
}

export function SkontoOpportunityWidget({
  daysAhead = 7,
  limit = 5,
  className,
}: SkontoOpportunityWidgetProps) {
  const { data: opportunities, isLoading, isError } = useUpcomingSkonto(daysAhead, limit);

  // Berechne Gesamtsumme
  const totalSavings = useMemo(() => {
    if (!opportunities) return 0;
    return opportunities.reduce((sum, opp) => sum + opp.skontoAmount, 0);
  }, [opportunities]);

  // Formatierte Gesamtsumme
  const formattedTotalSavings = useMemo(() => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(totalSavings);
  }, [totalSavings]);

  // Loading State
  if (isLoading) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingDown className="w-5 h-5" />
            Skonto-Gelegenheiten
          </CardTitle>
          <CardDescription>Bevorstehende Skonto-Fristen</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  // Error State
  if (isError) {
    return (
      <Card className={cn('border-destructive', className)}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="w-5 h-5" />
            Fehler beim Laden
          </CardTitle>
        </CardHeader>
      </Card>
    );
  }

  // Empty State
  if (!opportunities || opportunities.length === 0) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingDown className="w-5 h-5" />
            Skonto-Gelegenheiten
          </CardTitle>
          <CardDescription>Bevorstehende Skonto-Fristen</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-6 text-muted-foreground">
            <Clock className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Keine bevorstehenden Skonto-Fristen</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <TrendingDown className="w-5 h-5" />
              Skonto-Gelegenheiten
            </CardTitle>
            <CardDescription>
              {opportunities.length} Rechnung{opportunities.length !== 1 ? 'en' : ''} in den
              nächsten {daysAhead} Tagen
            </CardDescription>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted-foreground">Potenzielle Ersparnis</p>
            <p className="text-lg font-bold text-green-600">{formattedTotalSavings}</p>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="max-h-[300px]">
          <div className="space-y-3">
            {opportunities.map((opportunity) => (
              <OpportunityItem key={opportunity.invoiceId} opportunity={opportunity} />
            ))}
          </div>
        </ScrollArea>

        {/* View All Link */}
        {opportunities.length >= limit && (
          <div className="mt-4 pt-4 border-t">
            <Button variant="ghost" className="w-full gap-2" asChild>
              <Link to="/banking/skonto/upcoming">
                Alle anzeigen
                <ArrowRight className="w-4 h-4" />
              </Link>
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ==================== Sub-Components ====================

function OpportunityItem({ opportunity }: { opportunity: any }) {
  // Formatierte Deadline
  const formattedDeadline = useMemo(() => {
    const date = new Date(opportunity.skontoDeadline);
    return date.toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
    });
  }, [opportunity.skontoDeadline]);

  // Formatierter Betrag
  const formattedAmount = useMemo(() => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(opportunity.skontoAmount);
  }, [opportunity.skontoAmount]);

  // Colors basierend auf Urgency
  const colors = useMemo(() => {
    switch (opportunity.urgency) {
      case 'critical':
        return SKONTO_COLORS.expired; // Rot für kritisch
      case 'warning':
        return SKONTO_COLORS.expiring; // Gelb für Warnung
      default:
        return SKONTO_COLORS.active; // Grün für normal
    }
  }, [opportunity.urgency]);

  // Icon basierend auf Urgency
  const Icon = opportunity.urgency === 'critical' ? AlertTriangle : Clock;

  return (
    <Link
      to="/invoices"
      search={{ invoiceId: opportunity.invoiceId }}
      className={cn(
        'block p-3 rounded-lg border-l-4 transition-colors hover:bg-accent',
        colors.bg,
        colors.border
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Icon className={cn('w-4 h-4 shrink-0', colors.text)} />
            <p className="font-medium text-sm truncate">{opportunity.invoiceNumber}</p>
            <Badge variant="outline" className={cn('shrink-0', colors.badge)}>
              {opportunity.daysRemaining}{' '}
              {opportunity.daysRemaining === 1 ? 'Tag' : 'Tage'}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground truncate">
            {opportunity.entityName}
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-sm font-semibold text-green-600">{formattedAmount}</p>
          <p className="text-xs text-muted-foreground">bis {formattedDeadline}</p>
        </div>
      </div>
    </Link>
  );
}
