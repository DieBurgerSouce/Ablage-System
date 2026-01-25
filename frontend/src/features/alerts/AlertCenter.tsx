/**
 * Alert Center - Zentrales Alert-Dashboard
 *
 * Features:
 * - Ueberblick ueber alle Alerts mit Statistiken
 * - Filterung nach Kategorie, Schweregrad, Status
 * - Acknowledge/Dismiss/Resolve/Escalate Aktionen
 * - Bulk-Aktionen
 * - Echtzeit-Updates
 */

import { useState, useMemo } from "react";
import {
  AlertTriangle,
  Bell,
  CheckCircle,
  Clock,
  Filter,
  Shield,
  TrendingUp,
  XCircle,
  AlertCircle,
  FileWarning,
  Workflow,
  Zap,
  RefreshCw,
  ChevronDown,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import {
  useAlerts,
  useAlertStats,
  useAcknowledgeAlert,
  useDismissAlert,
  useResolveAlert,
  useBulkAction,
  type Alert,
  type AlertCategory,
  type AlertSeverity,
  type AlertStatus,
  type AlertFilters,
} from "./api/alerts-api";
import { AlertCard } from "./components/AlertCard";
import { AlertDetailDialog } from "./components/AlertDetailDialog";

// =============================================================================
// Category Configuration
// =============================================================================

const CATEGORY_CONFIG: Record<
  AlertCategory,
  { label: string; icon: typeof AlertTriangle; color: string }
> = {
  fraud: {
    label: "Betrug",
    icon: AlertTriangle,
    color: "text-red-500",
  },
  risk: {
    label: "Risiko",
    icon: TrendingUp,
    color: "text-orange-500",
  },
  compliance: {
    label: "Compliance",
    icon: Shield,
    color: "text-purple-500",
  },
  deadline: {
    label: "Fristen",
    icon: Clock,
    color: "text-yellow-500",
  },
  system: {
    label: "System",
    icon: Zap,
    color: "text-blue-500",
  },
  security: {
    label: "Sicherheit",
    icon: Shield,
    color: "text-red-600",
  },
  quality: {
    label: "Qualitaet",
    icon: FileWarning,
    color: "text-amber-500",
  },
  workflow: {
    label: "Workflow",
    icon: Workflow,
    color: "text-indigo-500",
  },
};

const SEVERITY_CONFIG: Record<
  AlertSeverity,
  { label: string; color: string; bgColor: string }
> = {
  info: {
    label: "Info",
    color: "text-gray-500",
    bgColor: "bg-gray-100 dark:bg-gray-800",
  },
  low: {
    label: "Niedrig",
    color: "text-green-500",
    bgColor: "bg-green-100 dark:bg-green-900/30",
  },
  medium: {
    label: "Mittel",
    color: "text-yellow-500",
    bgColor: "bg-yellow-100 dark:bg-yellow-900/30",
  },
  high: {
    label: "Hoch",
    color: "text-orange-500",
    bgColor: "bg-orange-100 dark:bg-orange-900/30",
  },
  critical: {
    label: "Kritisch",
    color: "text-red-500",
    bgColor: "bg-red-100 dark:bg-red-900/30",
  },
};

const STATUS_CONFIG: Record<
  AlertStatus,
  { label: string; color: string; icon: typeof Bell }
> = {
  new: { label: "Neu", color: "text-blue-500", icon: Bell },
  acknowledged: { label: "Gesehen", color: "text-yellow-500", icon: CheckCircle },
  in_progress: { label: "In Bearbeitung", color: "text-purple-500", icon: Clock },
  resolved: { label: "Geloest", color: "text-green-500", icon: CheckCircle },
  dismissed: { label: "Verworfen", color: "text-gray-500", icon: XCircle },
  escalated: { label: "Eskaliert", color: "text-red-500", icon: AlertCircle },
};

// =============================================================================
// Stats Cards Component
// =============================================================================

function StatsCards() {
  const { data: stats, isLoading } = useAlertStats();

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-4" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">Aktive Alerts</CardTitle>
          <Bell className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats?.total_active || 0}</div>
          <p className="text-xs text-muted-foreground">
            {stats?.new_count || 0} ungelesen
          </p>
        </CardContent>
      </Card>

      <Card className={stats?.critical_count ? "border-red-500" : ""}>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">Kritisch</CardTitle>
          <AlertTriangle className="h-4 w-4 text-red-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-red-500">
            {stats?.critical_count || 0}
          </div>
          <p className="text-xs text-muted-foreground">
            Sofortige Aufmerksamkeit erforderlich
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">Letzte 24h</CardTitle>
          <Clock className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {stats?.recent_24h_count || 0}
          </div>
          <p className="text-xs text-muted-foreground">Neue Alerts heute</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">Geloest</CardTitle>
          <CheckCircle className="h-4 w-4 text-green-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-green-500">
            {stats?.resolved_count || 0}
          </div>
          <p className="text-xs text-muted-foreground">
            {stats?.in_progress_count || 0} in Bearbeitung
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// =============================================================================
// Category Summary Component
// =============================================================================

function CategorySummary() {
  const { data: stats, isLoading } = useAlertStats();

  if (isLoading || !stats) {
    return null;
  }

  const categories = Object.entries(stats.by_category || {}).filter(
    ([_, count]) => count > 0
  );

  if (categories.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {categories.map(([category, count]) => {
        const config = CATEGORY_CONFIG[category as AlertCategory];
        if (!config) return null;
        const Icon = config.icon;

        return (
          <Badge
            key={category}
            variant="outline"
            className="flex items-center gap-1"
          >
            <Icon className={`h-3 w-3 ${config.color}`} />
            <span>{config.label}</span>
            <span className="ml-1 font-bold">{count}</span>
          </Badge>
        );
      })}
    </div>
  );
}

// =============================================================================
// Filter Bar Component
// =============================================================================

interface FilterBarProps {
  filters: AlertFilters;
  onFiltersChange: (filters: AlertFilters) => void;
  selectedCount: number;
  onBulkAction: (action: "acknowledge" | "dismiss" | "resolve") => void;
  isRefreshing: boolean;
  onRefresh: () => void;
}

function FilterBar({
  filters,
  onFiltersChange,
  selectedCount,
  onBulkAction,
  isRefreshing,
  onRefresh,
}: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="flex items-center gap-2">
        <Filter className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">Filter:</span>
      </div>

      <Select
        value={filters.category || "all"}
        onValueChange={(value) =>
          onFiltersChange({
            ...filters,
            category: value === "all" ? undefined : (value as AlertCategory),
            offset: 0,
          })
        }
      >
        <SelectTrigger className="w-[150px]">
          <SelectValue placeholder="Kategorie" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Alle Kategorien</SelectItem>
          {Object.entries(CATEGORY_CONFIG).map(([key, config]) => (
            <SelectItem key={key} value={key}>
              {config.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={filters.severity || "all"}
        onValueChange={(value) =>
          onFiltersChange({
            ...filters,
            severity: value === "all" ? undefined : (value as AlertSeverity),
            offset: 0,
          })
        }
      >
        <SelectTrigger className="w-[140px]">
          <SelectValue placeholder="Schweregrad" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Alle Schweregrade</SelectItem>
          {Object.entries(SEVERITY_CONFIG).map(([key, config]) => (
            <SelectItem key={key} value={key}>
              {config.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={filters.status || "all"}
        onValueChange={(value) =>
          onFiltersChange({
            ...filters,
            status: value === "all" ? undefined : (value as AlertStatus),
            offset: 0,
          })
        }
      >
        <SelectTrigger className="w-[150px]">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Alle Status</SelectItem>
          {Object.entries(STATUS_CONFIG).map(([key, config]) => (
            <SelectItem key={key} value={key}>
              {config.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="flex-1" />

      {selectedCount > 0 && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              {selectedCount} ausgewaehlt
              <ChevronDown className="ml-2 h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onClick={() => onBulkAction("acknowledge")}>
              <CheckCircle className="mr-2 h-4 w-4" />
              Alle bestaetigen
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onBulkAction("dismiss")}>
              <XCircle className="mr-2 h-4 w-4" />
              Alle verwerfen
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onBulkAction("resolve")}>
              <CheckCircle className="mr-2 h-4 w-4 text-green-500" />
              Alle loesen
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      <Button
        variant="outline"
        size="sm"
        onClick={onRefresh}
        disabled={isRefreshing}
      >
        <RefreshCw
          className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
        />
      </Button>
    </div>
  );
}

// =============================================================================
// Alert List Component
// =============================================================================

interface AlertListProps {
  alerts: Alert[];
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  onSelectAll: () => void;
  onClearSelection: () => void;
  onAlertClick: (alert: Alert) => void;
  onAcknowledge: (id: string) => void;
  onDismiss: (id: string) => void;
  onResolve: (id: string) => void;
  isLoading: boolean;
}

function AlertList({
  alerts,
  selectedIds,
  onToggleSelect,
  onSelectAll,
  onClearSelection,
  onAlertClick,
  onAcknowledge,
  onDismiss,
  onResolve,
  isLoading,
}: AlertListProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="p-4">
              <div className="flex items-start gap-4">
                <Skeleton className="h-5 w-5" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-5 w-3/4" />
                  <Skeleton className="h-4 w-1/2" />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <CheckCircle className="h-12 w-12 text-green-500 mb-4" />
          <h3 className="text-lg font-semibold">Keine Alerts</h3>
          <p className="text-muted-foreground">
            Derzeit sind keine Alerts vorhanden, die Ihren Filterkriterien
            entsprechen.
          </p>
        </CardContent>
      </Card>
    );
  }

  const allSelected = alerts.every((a) => selectedIds.has(a.id));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 px-2">
        <Checkbox
          checked={allSelected && alerts.length > 0}
          onCheckedChange={() => {
            if (allSelected) {
              onClearSelection();
            } else {
              onSelectAll();
            }
          }}
        />
        <span className="text-sm text-muted-foreground">
          {allSelected ? "Alle abwaehlen" : "Alle auswaehlen"}
        </span>
      </div>

      {alerts.map((alert) => (
        <AlertCard
          key={alert.id}
          alert={alert}
          isSelected={selectedIds.has(alert.id)}
          onToggleSelect={() => onToggleSelect(alert.id)}
          onClick={() => onAlertClick(alert)}
          onAcknowledge={() => onAcknowledge(alert.id)}
          onDismiss={() => onDismiss(alert.id)}
          onResolve={() => onResolve(alert.id)}
          categoryConfig={CATEGORY_CONFIG}
          severityConfig={SEVERITY_CONFIG}
          statusConfig={STATUS_CONFIG}
        />
      ))}
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function AlertCenter() {
  // State
  const [filters, setFilters] = useState<AlertFilters>({
    limit: 20,
    offset: 0,
    order_by: "created_at",
    order_desc: true,
  });
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [activeTab, setActiveTab] = useState("all");

  // Queries
  const { data, isLoading, refetch, isFetching } = useAlerts(filters);

  // Mutations
  const acknowledgeMutation = useAcknowledgeAlert();
  const dismissMutation = useDismissAlert();
  const resolveMutation = useResolveAlert();
  const bulkMutation = useBulkAction();

  // Handlers
  const handleFiltersChange = (newFilters: AlertFilters) => {
    setFilters(newFilters);
    setSelectedIds(new Set());
  };

  const handleToggleSelect = (id: string) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  };

  const handleSelectAll = () => {
    if (data?.alerts) {
      setSelectedIds(new Set(data.alerts.map((a) => a.id)));
    }
  };

  const handleClearSelection = () => {
    setSelectedIds(new Set());
  };

  const handleBulkAction = async (
    action: "acknowledge" | "dismiss" | "resolve"
  ) => {
    if (selectedIds.size === 0) return;

    await bulkMutation.mutateAsync({
      alert_ids: Array.from(selectedIds),
      action,
    });

    setSelectedIds(new Set());
  };

  const handleAcknowledge = async (id: string) => {
    await acknowledgeMutation.mutateAsync(id);
  };

  const handleDismiss = async (id: string) => {
    await dismissMutation.mutateAsync({ alertId: id });
  };

  const handleResolve = async (id: string) => {
    await resolveMutation.mutateAsync({ alertId: id });
  };

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    let newFilters: AlertFilters = {
      ...filters,
      offset: 0,
      category: undefined,
      status: undefined,
    };

    if (tab === "critical") {
      newFilters.severity = "critical";
    } else if (tab === "new") {
      newFilters.status = "new";
    } else if (tab === "fraud") {
      newFilters.category = "fraud";
    } else if (tab === "deadline") {
      newFilters.category = "deadline";
    } else if (tab === "resolved") {
      newFilters.status = "resolved";
    }

    setFilters(newFilters);
    setSelectedIds(new Set());
  };

  // Memoized alerts based on active tab filtering
  const alerts = useMemo(() => data?.alerts || [], [data?.alerts]);

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Alert Center</h1>
          <p className="text-muted-foreground">
            Zentrales Dashboard fuer alle Systemwarnungen und Benachrichtigungen
          </p>
        </div>
      </div>

      {/* Stats Cards */}
      <StatsCards />

      {/* Category Summary */}
      <CategorySummary />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="all">Alle</TabsTrigger>
          <TabsTrigger value="new" className="flex items-center gap-1">
            <Bell className="h-4 w-4" />
            Neu
          </TabsTrigger>
          <TabsTrigger value="critical" className="flex items-center gap-1">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            Kritisch
          </TabsTrigger>
          <TabsTrigger value="fraud" className="flex items-center gap-1">
            <Shield className="h-4 w-4" />
            Betrug
          </TabsTrigger>
          <TabsTrigger value="deadline" className="flex items-center gap-1">
            <Clock className="h-4 w-4" />
            Fristen
          </TabsTrigger>
          <TabsTrigger value="resolved" className="flex items-center gap-1">
            <CheckCircle className="h-4 w-4 text-green-500" />
            Geloest
          </TabsTrigger>
        </TabsList>

        <TabsContent value={activeTab} className="space-y-4">
          {/* Filter Bar */}
          <FilterBar
            filters={filters}
            onFiltersChange={handleFiltersChange}
            selectedCount={selectedIds.size}
            onBulkAction={handleBulkAction}
            isRefreshing={isFetching}
            onRefresh={() => refetch()}
          />

          {/* Alert List */}
          <AlertList
            alerts={alerts}
            selectedIds={selectedIds}
            onToggleSelect={handleToggleSelect}
            onSelectAll={handleSelectAll}
            onClearSelection={handleClearSelection}
            onAlertClick={setSelectedAlert}
            onAcknowledge={handleAcknowledge}
            onDismiss={handleDismiss}
            onResolve={handleResolve}
            isLoading={isLoading}
          />

          {/* Pagination */}
          {data && data.total > filters.limit! && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Zeige {filters.offset! + 1} -{" "}
                {Math.min(filters.offset! + filters.limit!, data.total)} von{" "}
                {data.total} Alerts
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={filters.offset === 0}
                  onClick={() =>
                    handleFiltersChange({
                      ...filters,
                      offset: Math.max(0, filters.offset! - filters.limit!),
                    })
                  }
                >
                  Zurueck
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={filters.offset! + filters.limit! >= data.total}
                  onClick={() =>
                    handleFiltersChange({
                      ...filters,
                      offset: filters.offset! + filters.limit!,
                    })
                  }
                >
                  Weiter
                </Button>
              </div>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Detail Dialog */}
      <AlertDetailDialog
        alert={selectedAlert}
        onClose={() => setSelectedAlert(null)}
        onAcknowledge={handleAcknowledge}
        onDismiss={handleDismiss}
        onResolve={handleResolve}
        categoryConfig={CATEGORY_CONFIG}
        severityConfig={SEVERITY_CONFIG}
        statusConfig={STATUS_CONFIG}
      />
    </div>
  );
}
