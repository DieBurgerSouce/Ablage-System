/**
 * Insight Card Component
 *
 * Zeigt einen einzelnen Daily Insight mit:
 * - Schweregrad-Badge, Titel, Zusammenfassung
 * - Aufklappbare Details (Erklaerung + Empfehlung)
 * - Beitragende Faktoren als Badges
 * - Impact-Wert und Frist
 */

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertCircle,
  AlertTriangle,
  TrendingDown,
  FileSignature,
  CreditCard,
  Receipt,
  Shield,
  Clock,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  Lightbulb,
} from "lucide-react";
import { Link } from "@tanstack/react-router";
import type { DailyInsight } from "../api/daily-briefing-api";

interface InsightCardProps {
  insight: DailyInsight;
}

const SEVERITY_CONFIG: Record<
  string,
  { label: string; variant: "destructive" | "default" | "secondary" | "outline"; className: string }
> = {
  critical: {
    label: "Kritisch",
    variant: "destructive",
    className: "",
  },
  high: {
    label: "Hoch",
    variant: "default",
    className: "bg-orange-600 hover:bg-orange-700",
  },
  medium: {
    label: "Mittel",
    variant: "secondary",
    className: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  },
  low: {
    label: "Niedrig",
    variant: "outline",
    className: "",
  },
};

const TYPE_ICONS: Record<string, React.ElementType> = {
  cashflow_warning: TrendingDown,
  contract_expiring: FileSignature,
  payment_risk: CreditCard,
  skonto_deadline: Receipt,
  compliance_reminder: Shield,
  overdue_invoice: AlertTriangle,
};

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(isoString: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleDateString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return isoString;
  }
}

export function InsightCard({ insight }: InsightCardProps) {
  const [expanded, setExpanded] = useState(false);

  const severity = SEVERITY_CONFIG[insight.severity] ?? SEVERITY_CONFIG.low;
  const Icon = TYPE_ICONS[insight.insight_type] ?? Lightbulb;
  const hasDetails = insight.explanation || insight.recommendation || insight.factors.length > 0;

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-4">
        {/* Header Row */}
        <div className="flex items-start gap-3">
          <div
            className={`p-2 rounded-lg flex-shrink-0 ${
              insight.severity === "critical"
                ? "bg-red-100 dark:bg-red-900/30"
                : insight.severity === "high"
                  ? "bg-orange-100 dark:bg-orange-900/30"
                  : insight.severity === "medium"
                    ? "bg-yellow-100 dark:bg-yellow-900/30"
                    : "bg-blue-100 dark:bg-blue-900/30"
            }`}
          >
            <Icon
              className={`h-5 w-5 ${
                insight.severity === "critical"
                  ? "text-red-600"
                  : insight.severity === "high"
                    ? "text-orange-600"
                    : insight.severity === "medium"
                      ? "text-yellow-600"
                      : "text-blue-600"
              }`}
            />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <h3 className="font-semibold text-sm">{insight.title}</h3>
              <Badge
                variant={severity.variant}
                className={`text-xs ${severity.className}`}
              >
                {severity.label}
              </Badge>
              {insight.confidence >= 0.8 && (
                <Badge variant="outline" className="text-xs">
                  {Math.round(insight.confidence * 100)}% Konfidenz
                </Badge>
              )}
            </div>

            <p className="text-sm text-muted-foreground">{insight.message}</p>

            {/* Metadata Row */}
            <div className="flex items-center gap-4 mt-2 flex-wrap">
              {insight.impact_value !== null && insight.impact_value > 0 && (
                <span className="text-sm font-medium text-green-600 dark:text-green-400">
                  {formatCurrency(insight.impact_value)} Impact
                </span>
              )}
              {insight.deadline && (
                <span className="flex items-center gap-1 text-sm text-muted-foreground">
                  <Clock className="h-3.5 w-3.5" />
                  Frist: {formatDate(insight.deadline)}
                </span>
              )}
              {insight.related_entity_name && (
                <span className="text-sm text-muted-foreground">
                  {insight.related_entity_name}
                </span>
              )}
            </div>
          </div>

          {/* Expand Button */}
          {hasDetails && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setExpanded(!expanded)}
              className="flex-shrink-0"
              aria-label={expanded ? "Details ausblenden" : "Details anzeigen"}
            >
              {expanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          )}
        </div>

        {/* Expanded Details */}
        {expanded && hasDetails && (
          <div className="mt-4 pl-12 space-y-3 border-t pt-3">
            {/* Explanation */}
            {insight.explanation && (
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
                  Erklaerung
                </h4>
                <p className="text-sm">{insight.explanation}</p>
              </div>
            )}

            {/* Recommendation */}
            {insight.recommendation && (
              <div className="bg-primary/5 rounded-lg p-3">
                <h4 className="text-xs font-semibold text-primary uppercase tracking-wider mb-1 flex items-center gap-1">
                  <AlertCircle className="h-3.5 w-3.5" />
                  Handlungsempfehlung
                </h4>
                <p className="text-sm">{insight.recommendation}</p>
              </div>
            )}

            {/* Contributing Factors */}
            {insight.factors.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Beitragende Faktoren
                </h4>
                <div className="flex flex-wrap gap-2">
                  {insight.factors.map((factor, idx) => (
                    <Badge
                      key={idx}
                      variant="outline"
                      className="text-xs"
                      title={factor.explanation}
                    >
                      {factor.name}: {factor.value}{" "}
                      <span className="ml-1 opacity-60">
                        ({Math.round(factor.contribution * 100)}%)
                      </span>
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Action Link */}
            {insight.action_url && (
              <Link
                to={insight.action_url}
                className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
              >
                Zur Aktion
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
