/**
 * AuditTimeline - Chronologische Ereignisliste
 *
 * Zeigt Audit-Eintraege als Timeline mit Filter-Optionen,
 * erweiterbaren Details und Merkle Proof Verifikation.
 */

import { useState } from "react";
import {
  Filter,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  User,
  Plus,
  Pencil,
  Trash2,
  Download,
  LogIn,
  Activity,
  Loader2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

import {
  useAuditEntries,
  type AuditEntry,
  type AuditEntryFilters,
} from "../api/audit-chain-api";
import { MerkleProofViewer } from "./MerkleProofViewer";

// =============================================================================
// Action Badge Config
// =============================================================================

interface ActionConfig {
  label: string;
  variant: "default" | "secondary" | "destructive" | "outline";
  icon: React.ComponentType<{ className?: string }>;
}

const ACTION_MAP: Record<string, ActionConfig> = {
  create: {
    label: "Erstellt",
    variant: "default",
    icon: Plus,
  },
  update: {
    label: "Bearbeitet",
    variant: "secondary",
    icon: Pencil,
  },
  delete: {
    label: "Geloescht",
    variant: "destructive",
    icon: Trash2,
  },
  export: {
    label: "Exportiert",
    variant: "outline",
    icon: Download,
  },
  login: {
    label: "Angemeldet",
    variant: "outline",
    icon: LogIn,
  },
  logout: {
    label: "Abgemeldet",
    variant: "outline",
    icon: LogIn,
  },
};

function getActionConfig(action: string): ActionConfig {
  // Match partial action names (e.g. "document_create" -> "create")
  for (const [key, config] of Object.entries(ACTION_MAP)) {
    if (action.toLowerCase().includes(key)) {
      return config;
    }
  }
  return {
    label: action,
    variant: "outline",
    icon: Activity,
  };
}

// =============================================================================
// Timeline Entry Component
// =============================================================================

interface TimelineEntryRowProps {
  entry: AuditEntry;
  onVerifyProof: (hash: string) => void;
}

function TimelineEntryRow({ entry, onVerifyProof }: TimelineEntryRowProps) {
  const [expanded, setExpanded] = useState(false);
  const actionConfig = getActionConfig(entry.action);
  const ActionIcon = actionConfig.icon;

  return (
    <div className="relative pl-8 pb-6 last:pb-0">
      {/* Timeline Line */}
      <div className="absolute left-3 top-0 bottom-0 w-px bg-border" />

      {/* Timeline Dot */}
      <div
        className={`absolute left-1.5 top-1.5 h-3 w-3 rounded-full border-2 border-background ${
          entry.success ? "bg-primary" : "bg-destructive"
        }`}
      />

      {/* Entry Content */}
      <div className="space-y-2">
        {/* Header Row */}
        <div className="flex items-start justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Timestamp */}
            <span className="text-xs font-mono text-muted-foreground">
              {new Date(entry.created_at).toLocaleString("de-DE", {
                day: "2-digit",
                month: "2-digit",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>

            {/* User */}
            <div className="flex items-center gap-1">
              <User className="h-3 w-3 text-muted-foreground" />
              <span className="text-sm">
                {entry.user_email || (
                  <span className="text-muted-foreground">System</span>
                )}
              </span>
            </div>
          </div>

          {/* Action Badge */}
          <Badge variant={actionConfig.variant} className="flex items-center gap-1">
            <ActionIcon className="h-3 w-3" />
            {actionConfig.label}
          </Badge>
        </div>

        {/* Entity Info */}
        {entry.resource_type && (
          <p className="text-sm text-muted-foreground">
            <span className="font-medium">{entry.resource_type}</span>
            {entry.resource_id && (
              <span className="font-mono ml-1">
                ({entry.resource_id.substring(0, 8)}...)
              </span>
            )}
          </p>
        )}

        {/* Actions Row */}
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? (
              <>
                <ChevronUp className="mr-1 h-3 w-3" /> Weniger
              </>
            ) : (
              <>
                <ChevronDown className="mr-1 h-3 w-3" /> Details
              </>
            )}
          </Button>

          {entry.integrity_hash && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => onVerifyProof(entry.integrity_hash!)}
            >
              <ShieldCheck className="mr-1 h-3 w-3" />
              Beweis pruefen
            </Button>
          )}
        </div>

        {/* Expanded Details */}
        {expanded && (
          <Card className="mt-2">
            <CardContent className="p-3 space-y-2 text-sm">
              {entry.ip_address && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">IP-Adresse</span>
                  <span className="font-mono">{entry.ip_address}</span>
                </div>
              )}
              {entry.integrity_hash && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    Integritaets-Hash
                  </span>
                  <span className="font-mono text-xs">
                    {entry.integrity_hash.substring(0, 16)}...
                  </span>
                </div>
              )}
              {!entry.success && entry.error_message && (
                <div>
                  <span className="text-muted-foreground">Fehler: </span>
                  <span className="text-destructive">
                    {entry.error_message}
                  </span>
                </div>
              )}
              {entry.metadata &&
                Object.keys(entry.metadata).length > 0 && (
                  <div>
                    <span className="text-muted-foreground block mb-1">
                      Metadaten:
                    </span>
                    <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
                      {JSON.stringify(entry.metadata, null, 2)}
                    </pre>
                  </div>
                )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function AuditTimeline() {
  const [filters, setFilters] = useState<AuditEntryFilters>({
    page: 1,
    per_page: 20,
    sort_order: "desc",
  });
  const [proofHash, setProofHash] = useState<string | null>(null);
  const [proofDialogOpen, setProofDialogOpen] = useState(false);

  const { data, isLoading, isFetching } = useAuditEntries(filters);

  const handleVerifyProof = (hash: string) => {
    setProofHash(hash);
    setProofDialogOpen(true);
  };

  const handleFilterChange = (partial: Partial<AuditEntryFilters>) => {
    setFilters((prev) => ({ ...prev, ...partial, page: 1 }));
  };

  const entries = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 0;

  return (
    <div className="space-y-4">
      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Filter:</span>
        </div>

        <Select
          value={filters.action || "all"}
          onValueChange={(value) =>
            handleFilterChange({
              action: value === "all" ? undefined : value,
            })
          }
        >
          <SelectTrigger
            className="w-[160px]"
            aria-label="Nach Aktion filtern"
          >
            <SelectValue placeholder="Aktion" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Aktionen</SelectItem>
            <SelectItem value="create">Erstellen</SelectItem>
            <SelectItem value="update">Bearbeiten</SelectItem>
            <SelectItem value="delete">Loeschen</SelectItem>
            <SelectItem value="export">Export</SelectItem>
            <SelectItem value="login">Anmeldung</SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={filters.resource_type || "all"}
          onValueChange={(value) =>
            handleFilterChange({
              resource_type: value === "all" ? undefined : value,
            })
          }
        >
          <SelectTrigger
            className="w-[160px]"
            aria-label="Nach Entitaetstyp filtern"
          >
            <SelectValue placeholder="Entitaet" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Entitaeten</SelectItem>
            <SelectItem value="document">Dokument</SelectItem>
            <SelectItem value="user">Benutzer</SelectItem>
            <SelectItem value="entity">Entitaet</SelectItem>
            <SelectItem value="invoice">Rechnung</SelectItem>
          </SelectContent>
        </Select>

        <Input
          type="date"
          className="w-[160px]"
          aria-label="Von Datum"
          placeholder="Von"
          value={filters.from_date ?? ""}
          onChange={(e) =>
            handleFilterChange({
              from_date: e.target.value || undefined,
            })
          }
        />

        <Input
          type="date"
          className="w-[160px]"
          aria-label="Bis Datum"
          placeholder="Bis"
          value={filters.to_date ?? ""}
          onChange={(e) =>
            handleFilterChange({
              to_date: e.target.value || undefined,
            })
          }
        />

        {isFetching && (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        )}
      </div>

      {/* Timeline */}
      {isLoading ? (
        <div className="space-y-4 pl-8">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-4 w-64" />
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-4 w-32" />
            </div>
          ))}
        </div>
      ) : entries.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Activity className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold">
              Keine Eintraege gefunden
            </h3>
            <p className="text-muted-foreground text-sm">
              Es wurden keine Audit-Eintraege gefunden, die Ihren
              Filterkriterien entsprechen.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="relative">
          {entries.map((entry) => (
            <TimelineEntryRow
              key={entry.id}
              entry={entry}
              onVerifyProof={handleVerifyProof}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {total > (filters.per_page ?? 20) && (
        <div className="flex items-center justify-between pt-2">
          <p className="text-sm text-muted-foreground">
            Seite {filters.page ?? 1} von {totalPages} ({total} Eintraege
            gesamt)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={(filters.page ?? 1) <= 1}
              aria-label="Vorherige Seite"
              onClick={() =>
                setFilters((prev) => ({
                  ...prev,
                  page: Math.max(1, (prev.page ?? 1) - 1),
                }))
              }
            >
              Zurueck
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={(filters.page ?? 1) >= totalPages}
              aria-label="Naechste Seite"
              onClick={() =>
                setFilters((prev) => ({
                  ...prev,
                  page: (prev.page ?? 1) + 1,
                }))
              }
            >
              Weiter
            </Button>
          </div>
        </div>
      )}

      {/* Merkle Proof Dialog */}
      <MerkleProofViewer
        entryHash={proofHash}
        open={proofDialogOpen}
        onOpenChange={setProofDialogOpen}
      />
    </div>
  );
}
