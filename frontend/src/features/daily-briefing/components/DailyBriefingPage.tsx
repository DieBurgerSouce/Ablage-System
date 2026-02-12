/**
 * Daily Briefing Page
 *
 * Hauptseite für das KI-Tagesbriefing.
 * Zeigt Zusammenfassung, kategorisierte Tabs und Insight-Karten.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Sparkles, RefreshCw, AlertCircle } from "lucide-react";
import {
  useDailyInsights,
  useGenerateDailyInsights,
  INSIGHT_TYPES,
  INSIGHT_TYPE_LABELS,
} from "../api/daily-briefing-api";
import type { InsightType, DailyInsight } from "../api/daily-briefing-api";
import { BriefingSummary } from "./BriefingSummary";
import { InsightCard } from "./InsightCard";

function formatCurrentDate(): string {
  return new Date().toLocaleDateString("de-DE", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

type TabValue = "all" | InsightType;

const TAB_CONFIG: { value: TabValue; label: string }[] = [
  { value: "all", label: "Alle" },
  ...INSIGHT_TYPES.map((type) => ({
    value: type as TabValue,
    label: INSIGHT_TYPE_LABELS[type],
  })),
];

function filterInsights(
  insights: DailyInsight[],
  tab: TabValue
): DailyInsight[] {
  if (tab === "all") return insights;
  return insights.filter((i) => i.insight_type === tab);
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      {/* Summary skeleton */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
      {/* Cards skeleton */}
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-32 rounded-lg" />
        ))}
      </div>
    </div>
  );
}

export function DailyBriefingPage() {
  const [activeTab, setActiveTab] = useState<TabValue>("all");

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useDailyInsights();

  const generateMutation = useGenerateDailyInsights();

  const handleGenerate = () => {
    generateMutation.mutate();
  };

  const _filteredInsights = data
    ? filterInsights(data.insights, activeTab)
    : [];

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <Sparkles className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-3xl font-bold">Tagesbriefing</h1>
            <p className="text-muted-foreground">{formatCurrentDate()}</p>
          </div>
        </div>
        <Button
          onClick={handleGenerate}
          disabled={generateMutation.isPending}
          variant="outline"
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${generateMutation.isPending ? "animate-spin" : ""}`}
          />
          {generateMutation.isPending
            ? "Generierung läuft..."
            : "Neu generieren"}
        </Button>
      </div>

      {/* Generation success message */}
      {generateMutation.isSuccess && generateMutation.data && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {generateMutation.data.total_generated} Insights wurden in{" "}
            {generateMutation.data.duration_ms}ms generiert.
          </AlertDescription>
        </Alert>
      )}

      {/* Error state */}
      {isError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Insights konnten nicht geladen werden:{" "}
            {error instanceof Error ? error.message : "Unbekannter Fehler"}
            <Button
              variant="link"
              size="sm"
              onClick={() => refetch()}
              className="ml-2"
            >
              Erneut versuchen
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Loading state */}
      {isLoading && <LoadingSkeleton />}

      {/* Main content */}
      {data && !isLoading && (
        <>
          {/* Summary Cards */}
          <BriefingSummary data={data} />

          {/* Tabs with insight categories */}
          <Tabs
            value={activeTab}
            onValueChange={(v) => setActiveTab(v as TabValue)}
          >
            <TabsList className="flex-wrap h-auto gap-1">
              {TAB_CONFIG.map((tab) => {
                const count =
                  tab.value === "all"
                    ? data.total_count
                    : (data.by_type[tab.value] ?? 0);

                return (
                  <TabsTrigger
                    key={tab.value}
                    value={tab.value}
                    className="gap-1"
                  >
                    {tab.label}
                    {count > 0 && (
                      <span className="text-xs opacity-70">({count})</span>
                    )}
                  </TabsTrigger>
                );
              })}
            </TabsList>

            {/* Single content area for all tabs */}
            {TAB_CONFIG.map((tab) => (
              <TabsContent key={tab.value} value={tab.value}>
                <InsightList
                  insights={filterInsights(data.insights, tab.value)}
                  emptyMessage={
                    tab.value === "all"
                      ? "Aktuell gibt es keine Insights. Alle Systeme laufen normal."
                      : `Keine ${tab.label}-Insights vorhanden.`
                  }
                />
              </TabsContent>
            ))}
          </Tabs>
        </>
      )}
    </div>
  );
}

function InsightList({
  insights,
  emptyMessage,
}: {
  insights: DailyInsight[];
  emptyMessage: string;
}) {
  if (insights.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Sparkles className="h-12 w-12 mx-auto mb-3 opacity-30" />
        <p>{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3 mt-4">
      {insights.map((insight) => (
        <InsightCard key={insight.id} insight={insight} />
      ))}
    </div>
  );
}
