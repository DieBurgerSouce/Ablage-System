/**
 * Briefing Summary Component
 *
 * Zeigt 4 KPI-Karten (eine pro Schweregrad) mit Anzahl,
 * einen Gesundheitsindikator und den Zeitpunkt der letzten Generierung.
 */

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  AlertCircle,
  AlertTriangle,
  Info,
  CheckCircle2,
  Clock,
} from "lucide-react";
import type { DailyInsightListResponse } from "../api/daily-briefing-api";

interface BriefingSummaryProps {
  data: DailyInsightListResponse;
}

interface SeverityCard {
  label: string;
  key: string;
  icon: React.ElementType;
  color: string;
  bgColor: string;
  borderColor: string;
}

const SEVERITY_CARDS: SeverityCard[] = [
  {
    label: "Kritisch",
    key: "critical",
    icon: AlertCircle,
    color: "text-red-600 dark:text-red-400",
    bgColor: "bg-red-50 dark:bg-red-950",
    borderColor: "border-red-200 dark:border-red-800",
  },
  {
    label: "Hoch",
    key: "high",
    icon: AlertTriangle,
    color: "text-orange-600 dark:text-orange-400",
    bgColor: "bg-orange-50 dark:bg-orange-950",
    borderColor: "border-orange-200 dark:border-orange-800",
  },
  {
    label: "Mittel",
    key: "medium",
    icon: Info,
    color: "text-yellow-600 dark:text-yellow-400",
    bgColor: "bg-yellow-50 dark:bg-yellow-950",
    borderColor: "border-yellow-200 dark:border-yellow-800",
  },
  {
    label: "Niedrig",
    key: "low",
    icon: CheckCircle2,
    color: "text-blue-600 dark:text-blue-400",
    bgColor: "bg-blue-50 dark:bg-blue-950",
    borderColor: "border-blue-200 dark:border-blue-800",
  },
];

function getHealthStatus(bySeverity: Record<string, number>): {
  label: string;
  color: string;
} {
  const critical = bySeverity.critical ?? 0;
  const high = bySeverity.high ?? 0;

  if (critical > 0) return { label: "Sofortiger Handlungsbedarf", color: "text-red-600" };
  if (high > 2) return { label: "Erhöhte Aufmerksamkeit", color: "text-orange-600" };
  if (high > 0) return { label: "Überwachung empfohlen", color: "text-yellow-600" };
  return { label: "Alles in Ordnung", color: "text-green-600" };
}

function formatGeneratedAt(isoString: string | null): string {
  if (!isoString) return "Unbekannt";
  try {
    const date = new Date(isoString);
    return date.toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "Unbekannt";
  }
}

export function BriefingSummary({ data }: BriefingSummaryProps) {
  const health = getHealthStatus(data.by_severity);

  return (
    <div className="space-y-4">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {SEVERITY_CARDS.map((card) => {
          const count = data.by_severity[card.key] ?? 0;
          const Icon = card.icon;

          return (
            <Card
              key={card.key}
              className={`${card.bgColor} ${card.borderColor}`}
            >
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      {card.label}
                    </p>
                    <p className={`text-3xl font-bold ${card.color}`}>
                      {count}
                    </p>
                  </div>
                  <Icon className={`h-8 w-8 ${card.color} opacity-50`} />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Health + Generation Time */}
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className={health.color}>
            {health.label}
          </Badge>
          <span className="text-muted-foreground">
            {data.total_count} Insights gesamt
          </span>
        </div>
        <div className="flex items-center gap-1 text-muted-foreground">
          <Clock className="h-3.5 w-3.5" />
          <span>Generiert: {formatGeneratedAt(data.generated_at)}</span>
        </div>
      </div>
    </div>
  );
}
