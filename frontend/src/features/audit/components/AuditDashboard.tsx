/**
 * Audit Dashboard - Audit-Protokoll Dashboard
 *
 * Features:
 * - Uebersicht ueber alle Audit-Logs
 * - Filterung nach Aktion, Ressource, Status, Datum
 * - Export als CSV/JSON
 * - Echtzeit-Updates
 */

import { useState } from "react";
import {
  Shield,
  Users,
  Activity,
  AlertTriangle,
  Download,
  FileText,
  Filter,
  RefreshCw,
  Calendar,
  CheckCircle,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import {
  useAuditLogs,
  useAuditStats,
  type AuditFilters,
  type AuditLogView,
} from "../api/audit-api";

// =============================================================================
// Stats Cards Component
// =============================================================================

function StatsCards() {
  const { data: stats, isLoading } = useAuditStats(30);

  if (isLoading) {
    return (
      <div
        className="grid gap-4 md:grid-cols-2 lg:grid-cols-4"
        role="region"
        aria-label="Audit-Statistiken werden geladen"
      >
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-4" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
              <Skeleton className="h-3 w-20 mt-1" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const todayEvents =
    stats?.events_by_day?.[new Date().toISOString().split("T")[0]] || 0;
  const failedEvents = Object.entries(stats?.events_by_type || {})
    .filter(([type]) => type.includes("failed") || type.includes("error"))
    .reduce((sum, [, count]) => sum + count, 0);

  return (
    <div
      className="grid gap-4 md:grid-cols-2 lg:grid-cols-4"
      role="region"
      aria-label="Audit-Statistiken"
    >
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">Gesamte Events</CardTitle>
          <Activity className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats?.total_events || 0}</div>
          <p className="text-xs text-muted-foreground">Letzte 30 Tage</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">Aktive Nutzer</CardTitle>
          <Users className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {stats?.unique_actors || 0}
          </div>
          <p className="text-xs text-muted-foreground">
            Verschiedene Akteure
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">Events heute</CardTitle>
          <Calendar className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{todayEvents}</div>
          <p className="text-xs text-muted-foreground">
            {new Date().toLocaleDateString("de-DE")}
          </p>
        </CardContent>
      </Card>

      <Card className={failedEvents > 0 ? "border-red-500" : ""}>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">
            Fehlgeschlagen
          </CardTitle>
          <AlertTriangle className="h-4 w-4 text-red-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-red-500">{failedEvents}</div>
          <p className="text-xs text-muted-foreground">
            Fehlerhafte Aktionen
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// =============================================================================
// Filter Bar Component
// =============================================================================

interface FilterBarProps {
  filters: AuditFilters;
  onFiltersChange: (filters: AuditFilters) => void;
  isRefreshing: boolean;
  onRefresh: () => void;
  onExport: (format: "csv" | "json") => void;
}

function FilterBar({
  filters,
  onFiltersChange,
  isRefreshing,
  onRefresh,
  onExport,
}: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="flex items-center gap-2">
        <Filter className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">Filter:</span>
      </div>

      <Select
        value={filters.action || "all"}
        onValueChange={(value) =>
          onFiltersChange({
            ...filters,
            action: value === "all" ? undefined : value,
            page: 1,
          })
        }
      >
        <SelectTrigger className="w-[180px]" aria-label="Nach Aktion filtern">
          <SelectValue placeholder="Aktion" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Alle Aktionen</SelectItem>
          <SelectItem value="login">Login</SelectItem>
          <SelectItem value="logout">Logout</SelectItem>
          <SelectItem value="create">Erstellen</SelectItem>
          <SelectItem value="update">Aktualisieren</SelectItem>
          <SelectItem value="delete">Loeschen</SelectItem>
          <SelectItem value="export">Export</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={filters.resource_type || "all"}
        onValueChange={(value) =>
          onFiltersChange({
            ...filters,
            resource_type: value === "all" ? undefined : value,
            page: 1,
          })
        }
      >
        <SelectTrigger
          className="w-[180px]"
          aria-label="Nach Ressourcentyp filtern"
        >
          <SelectValue placeholder="Ressource" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Alle Ressourcen</SelectItem>
          <SelectItem value="document">Dokument</SelectItem>
          <SelectItem value="user">Benutzer</SelectItem>
          <SelectItem value="entity">Entitaet</SelectItem>
          <SelectItem value="invoice">Rechnung</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={
          filters.success === undefined
            ? "all"
            : filters.success
              ? "success"
              : "failed"
        }
        onValueChange={(value) =>
          onFiltersChange({
            ...filters,
            success:
              value === "all"
                ? undefined
                : value === "success"
                  ? true
                  : false,
            page: 1,
          })
        }
      >
        <SelectTrigger className="w-[150px]" aria-label="Nach Status filtern">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Alle Status</SelectItem>
          <SelectItem value="success">Erfolgreich</SelectItem>
          <SelectItem value="failed">Fehlgeschlagen</SelectItem>
        </SelectContent>
      </Select>

      <div className="flex-1" />

      <Button
        variant="outline"
        size="sm"
        onClick={() => onExport("csv")}
        aria-label="Als CSV exportieren"
      >
        <Download className="mr-2 h-4 w-4" />
        CSV
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={() => onExport("json")}
        aria-label="Als JSON exportieren"
      >
        <FileText className="mr-2 h-4 w-4" />
        JSON
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={onRefresh}
        disabled={isRefreshing}
        aria-label="Audit-Logs aktualisieren"
      >
        <RefreshCw
          className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
        />
      </Button>
    </div>
  );
}

// =============================================================================
// Audit Table Component
// =============================================================================

interface AuditTableProps {
  logs: AuditLogView[];
  isLoading: boolean;
}

function AuditTable({ logs, isLoading }: AuditTableProps) {
  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="space-y-4">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-6 w-20" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (logs.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <Shield className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">Keine Audit-Eintraege gefunden</h3>
          <p className="text-muted-foreground">
            Es wurden keine Eintraege gefunden, die Ihren Filterkriterien
            entsprechen.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Zeitpunkt</TableHead>
                <TableHead>Benutzer</TableHead>
                <TableHead>Aktion</TableHead>
                <TableHead>Ressource</TableHead>
                <TableHead>IP-Adresse</TableHead>
                <TableHead>Erfolg</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.map((log) => (
                <TableRow key={log.id}>
                  <TableCell className="font-mono text-sm">
                    {new Date(log.created_at).toLocaleString("de-DE", {
                      year: "numeric",
                      month: "2-digit",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </TableCell>
                  <TableCell>
                    {log.user_email || log.user_id || (
                      <span className="text-muted-foreground">System</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{log.action}</Badge>
                  </TableCell>
                  <TableCell>
                    {log.resource_type ? (
                      <div className="space-y-1">
                        <div className="font-medium">{log.resource_type}</div>
                        {log.resource_id && (
                          <div className="text-xs text-muted-foreground font-mono">
                            {log.resource_id.substring(0, 8)}...
                          </div>
                        )}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-sm">
                    {log.ip_address || (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {log.success ? (
                      <Badge
                        variant="outline"
                        className="bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
                      >
                        <CheckCircle className="mr-1 h-3 w-3" />
                        Erfolg
                      </Badge>
                    ) : (
                      <Badge
                        variant="outline"
                        className="bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300"
                      >
                        <XCircle className="mr-1 h-3 w-3" />
                        Fehler
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function AuditDashboard() {
  // State
  const [filters, setFilters] = useState<AuditFilters>({
    page: 1,
    per_page: 20,
    sort_by: "created_at",
    sort_order: "desc",
  });

  // Queries
  const { data, isLoading, refetch, isFetching } = useAuditLogs(filters);

  // Handlers
  const handleFiltersChange = (newFilters: AuditFilters) => {
    setFilters(newFilters);
  };

  const handleExport = (format: "csv" | "json") => {
    if (!data?.items || data.items.length === 0) return;

    const logs = data.items;

    if (format === "csv") {
      const headers = [
        "Zeitpunkt",
        "Benutzer",
        "Aktion",
        "Ressourcentyp",
        "Ressourcen-ID",
        "IP-Adresse",
        "Erfolg",
        "Fehlermeldung",
      ];

      const rows = logs.map((log) => [
        new Date(log.created_at).toISOString(),
        log.user_email || log.user_id || "System",
        log.action,
        log.resource_type || "",
        log.resource_id || "",
        log.ip_address || "",
        log.success ? "Ja" : "Nein",
        log.error_message || "",
      ]);

      const csv = [
        headers.join(","),
        ...rows.map((row) =>
          row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")
        ),
      ].join("\n");

      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `audit-log-${new Date().toISOString()}.csv`;
      link.click();
    } else if (format === "json") {
      const json = JSON.stringify(logs, null, 2);
      const blob = new Blob([json], { type: "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `audit-log-${new Date().toISOString()}.json`;
      link.click();
    }
  };

  const logs = data?.items || [];
  const total = data?.total || 0;
  const totalPages = data?.total_pages || 0;

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Audit-Protokoll</h1>
          <p className="text-muted-foreground">
            Vollstaendige Uebersicht aller Systemaktivitaeten und
            Benutzeraktionen
          </p>
        </div>
      </div>

      {/* Stats Cards */}
      <StatsCards />

      {/* Filter Bar */}
      <FilterBar
        filters={filters}
        onFiltersChange={handleFiltersChange}
        isRefreshing={isFetching}
        onRefresh={() => refetch()}
        onExport={handleExport}
      />

      {/* Audit Table */}
      <AuditTable logs={logs} isLoading={isLoading} />

      {/* Pagination */}
      {total > filters.per_page! && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Seite {filters.page} von {totalPages} ({total} Eintraege gesamt)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={filters.page === 1}
              aria-label="Vorherige Seite"
              onClick={() =>
                handleFiltersChange({
                  ...filters,
                  page: Math.max(1, (filters.page || 1) - 1),
                })
              }
            >
              Zurueck
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={filters.page === totalPages}
              aria-label="Naechste Seite"
              onClick={() =>
                handleFiltersChange({
                  ...filters,
                  page: (filters.page || 1) + 1,
                })
              }
            >
              Weiter
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
