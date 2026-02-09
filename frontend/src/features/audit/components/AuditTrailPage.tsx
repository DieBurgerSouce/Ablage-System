/**
 * AuditTrailPage - Hauptseite des Audit-Trail-Viewers
 *
 * Zeigt eine Tab-Navigation mit Protokoll, Integritaet und Export.
 * Enthalt Header mit Integritaets-Score Badge.
 */

import {
  Shield,
  Activity,
  ShieldCheck,
  Download,
  Loader2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import { useAuditChainStatus } from "../api/audit-chain-api";
import { AuditTimeline } from "./AuditTimeline";
import { IntegrityReportPanel } from "./IntegrityReportPanel";
import { AuditExportPanel } from "./AuditExportPanel";

// =============================================================================
// Score Badge
// =============================================================================

function IntegrityBadge() {
  const { data: status, isLoading } = useAuditChainStatus();

  if (isLoading) {
    return <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />;
  }

  if (!status) return null;

  const score = status.integrity_score;
  let variant: "default" | "secondary" | "destructive";
  let label: string;

  if (score >= 95) {
    variant = "default";
    label = `${score.toFixed(0)}% Integritaet`;
  } else if (score >= 80) {
    variant = "secondary";
    label = `${score.toFixed(0)}% Integritaet`;
  } else {
    variant = "destructive";
    label = `${score.toFixed(0)}% Integritaet`;
  }

  return (
    <Badge variant={variant} className="flex items-center gap-1">
      <ShieldCheck className="h-3 w-3" />
      {label}
    </Badge>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function AuditTrailPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Shield className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-3xl font-bold tracking-tight">
              Audit-Trail
            </h1>
            <p className="text-muted-foreground">
              Kryptografisch gesicherte Protokollierung aller
              Systemaktivitaeten
            </p>
          </div>
        </div>
        <IntegrityBadge />
      </div>

      {/* Tabs */}
      <Tabs defaultValue="protokoll" className="space-y-4">
        <TabsList>
          <TabsTrigger value="protokoll" className="flex items-center gap-1.5">
            <Activity className="h-4 w-4" />
            Protokoll
          </TabsTrigger>
          <TabsTrigger
            value="integritaet"
            className="flex items-center gap-1.5"
          >
            <ShieldCheck className="h-4 w-4" />
            Integritaet
          </TabsTrigger>
          <TabsTrigger value="export" className="flex items-center gap-1.5">
            <Download className="h-4 w-4" />
            Export
          </TabsTrigger>
        </TabsList>

        <TabsContent value="protokoll">
          <AuditTimeline />
        </TabsContent>

        <TabsContent value="integritaet">
          <IntegrityReportPanel />
        </TabsContent>

        <TabsContent value="export">
          <AuditExportPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
