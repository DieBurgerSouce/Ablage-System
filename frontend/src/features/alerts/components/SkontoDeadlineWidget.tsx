/**
 * SkontoDeadlineWidget - Widget für ablaufende Skonto-Fristen im Alert Center
 *
 * Zeigt kompakte Übersicht aller bald ablaufenden Skonto-Fristen.
 * Kann in Alert Center Dashboard oder auf der Startseite eingebunden werden.
 *
 * Features:
 * - Gruppierung nach Dringlichkeit (heute, diese Woche, später)
 * - Gesamtersparnis-Anzeige
 * - Quick-Actions pro Rechnung
 * - Link zu Skonto-Übersicht
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  Clock,
  AlertTriangle,
  TrendingDown,
  ChevronRight,
  Calendar,
  Euro,
  ExternalLink,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// =============================================================================
// Types
// =============================================================================

interface SkontoDeadline {
  invoice_id: string;
  invoice_number: string;
  entity_name: string;
  gross_amount: number;
  skonto_percentage: number;
  skonto_amount: number;
  deadline: string;
  days_remaining: number;
}

interface SkontoDeadlinesResponse {
  deadlines: SkontoDeadline[];
  total: number;
  total_potential_savings: number;
  critical_count: number; // heute
  warning_count: number; // < 3 Tage
}

// =============================================================================
// API
// =============================================================================

async function fetchUpcomingSkontoDeadlines(): Promise<SkontoDeadlinesResponse> {
  const response = await fetch("/api/v1/invoices/skonto/upcoming?days=14", {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Fehler beim Laden der Skonto-Fristen");
  }

  return response.json();
}

// =============================================================================
// Deadline Item Component
// =============================================================================

interface DeadlineItemProps {
  deadline: SkontoDeadline;
}

function DeadlineItem({ deadline }: DeadlineItemProps) {
  const urgency =
    deadline.days_remaining <= 0
      ? "expired"
      : deadline.days_remaining <= 1
      ? "critical"
      : deadline.days_remaining <= 3
      ? "warning"
      : "normal";

  const urgencyStyles = {
    expired: "border-l-gray-400 bg-gray-50 dark:bg-gray-900/20",
    critical: "border-l-red-500 bg-red-50 dark:bg-red-900/20",
    warning: "border-l-yellow-500 bg-yellow-50 dark:bg-yellow-900/20",
    normal: "border-l-blue-500 bg-blue-50 dark:bg-blue-900/20",
  };

  const urgencyBadge = {
    expired: { label: "Abgelaufen", variant: "destructive" as const },
    critical: { label: "Heute", variant: "destructive" as const },
    warning: {
      label: `${deadline.days_remaining} Tage`,
      variant: "secondary" as const,
    },
    normal: {
      label: `${deadline.days_remaining} Tage`,
      variant: "outline" as const,
    },
  };

  const formattedAmount = new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
  }).format(deadline.skonto_amount);

  const formattedDate = new Date(deadline.deadline).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
  });

  return (
    <div
      className={cn(
        "flex items-center gap-3 px-3 py-2 border-l-4 rounded-r-md",
        urgencyStyles[urgency]
      )}
    >
      {/* Icon */}
      <div className="shrink-0">
        {urgency === "critical" || urgency === "expired" ? (
          <AlertTriangle className="h-4 w-4 text-red-500" />
        ) : (
          <Clock className="h-4 w-4 text-yellow-500" />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm truncate">
            {deadline.invoice_number}
          </span>
          <Badge variant={urgencyBadge[urgency].variant} className="text-xs">
            {urgencyBadge[urgency].label}
          </Badge>
        </div>
        <div className="text-xs text-muted-foreground truncate">
          {deadline.entity_name}
        </div>
      </div>

      {/* Savings */}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="shrink-0 text-right">
              <div className="text-sm font-semibold text-green-600 dark:text-green-400">
                {formattedAmount}
              </div>
              <div className="text-xs text-muted-foreground">
                {deadline.skonto_percentage}% bis {formattedDate}
              </div>
            </div>
          </TooltipTrigger>
          <TooltipContent>
            <p>
              {deadline.skonto_percentage}% Skonto auf{" "}
              {new Intl.NumberFormat("de-DE", {
                style: "currency",
                currency: "EUR",
              }).format(deadline.gross_amount)}
            </p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {/* Link */}
      <Link
        to="/invoices/$invoiceId"
        params={{ invoiceId: deadline.invoice_id }}
        className="shrink-0"
      >
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <ChevronRight className="h-4 w-4" />
        </Button>
      </Link>
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

interface SkontoDeadlineWidgetProps {
  maxItems?: number;
  showHeader?: boolean;
  className?: string;
}

export function SkontoDeadlineWidget({
  maxItems = 5,
  showHeader = true,
  className,
}: SkontoDeadlineWidgetProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["skonto-deadlines-widget"],
    queryFn: fetchUpcomingSkontoDeadlines,
    refetchInterval: 60000, // Refresh every minute
  });

  if (isLoading) {
    return (
      <Card className={className}>
        {showHeader && (
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Skeleton className="h-4 w-4" />
              <Skeleton className="h-4 w-32" />
            </CardTitle>
          </CardHeader>
        )}
        <CardContent className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={className}>
        <CardContent className="py-6 text-center text-muted-foreground">
          <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-yellow-500" />
          <p className="text-sm">Fehler beim Laden der Skonto-Fristen</p>
        </CardContent>
      </Card>
    );
  }

  if (!data || data.deadlines.length === 0) {
    return (
      <Card className={className}>
        {showHeader && (
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-green-500" />
              Skonto-Fristen
            </CardTitle>
          </CardHeader>
        )}
        <CardContent className="py-6 text-center text-muted-foreground">
          <Clock className="h-8 w-8 mx-auto mb-2 text-gray-400" />
          <p className="text-sm">Keine ablaufenden Skonto-Fristen</p>
        </CardContent>
      </Card>
    );
  }

  const displayedDeadlines = data.deadlines.slice(0, maxItems);
  const hasMore = data.deadlines.length > maxItems;

  const formattedTotalSavings = new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
  }).format(data.total_potential_savings);

  return (
    <Card className={className}>
      {showHeader && (
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-green-500" />
              Skonto-Fristen
              {data.critical_count > 0 && (
                <Badge variant="destructive" className="text-xs">
                  {data.critical_count} dringend
                </Badge>
              )}
            </CardTitle>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1 text-sm text-green-600 dark:text-green-400 font-semibold">
                    <Euro className="h-3.5 w-3.5" />
                    {formattedTotalSavings}
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Potenzielle Gesamtersparnis bei {data.total} Rechnungen</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </CardHeader>
      )}

      <CardContent className="space-y-2">
        {displayedDeadlines.map((deadline) => (
          <DeadlineItem key={deadline.invoice_id} deadline={deadline} />
        ))}

        {hasMore && (
          <Link to="/invoices" search={{ skonto_pending: true }}>
            <Button variant="ghost" className="w-full text-sm gap-2">
              <Calendar className="h-4 w-4" />
              Alle {data.total} Fristen anzeigen
              <ExternalLink className="h-3 w-3" />
            </Button>
          </Link>
        )}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Compact Version for Sidebar/Header
// =============================================================================

export function SkontoDeadlineCompact() {
  const { data } = useQuery({
    queryKey: ["skonto-deadlines-widget"],
    queryFn: fetchUpcomingSkontoDeadlines,
    refetchInterval: 60000,
  });

  if (!data || data.total === 0) {
    return null;
  }

  const formattedSavings = new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
  }).format(data.total_potential_savings);

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Link to="/invoices" search={{ skonto_pending: true }}>
            <Button
              variant="ghost"
              size="sm"
              className={cn(
                "gap-2",
                data.critical_count > 0 && "text-red-500 hover:text-red-600"
              )}
            >
              <TrendingDown className="h-4 w-4" />
              <span className="font-medium">{data.total}</span>
              {data.critical_count > 0 && (
                <Badge variant="destructive" className="text-xs px-1.5 py-0">
                  {data.critical_count}
                </Badge>
              )}
            </Button>
          </Link>
        </TooltipTrigger>
        <TooltipContent>
          <p>
            {data.total} Skonto-Fristen ({formattedSavings} Ersparnis möglich)
          </p>
          {data.critical_count > 0 && (
            <p className="text-red-400">
              {data.critical_count} laufen heute ab!
            </p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
