/**
 * IntegrityReportPanel - Integritätsbericht
 *
 * Zeigt Integritäts-Score, Root Hash, Verletzungen
 * und Verifikations-Status der Audit-Chain.
 */

import { useState } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Copy,
  CheckCircle,
  AlertTriangle,
  Clock,
  AlertCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

import { useIntegrityReport } from "../api/audit-chain-api";

// =============================================================================
// Score Display
// =============================================================================

function IntegrityScore({ score }: { score: number }) {
  let colorClass: string;
  let label: string;

  if (score >= 95) {
    colorClass = "text-green-600";
    label = "Ausgezeichnet";
  } else if (score >= 80) {
    colorClass = "text-yellow-600";
    label = "Akzeptabel";
  } else {
    colorClass = "text-red-600";
    label = "Kritisch";
  }

  return (
    <div className="text-center space-y-3">
      <div className={`text-5xl font-bold tabular-nums ${colorClass}`}>
        {score.toFixed(1)}
      </div>
      <p className="text-sm text-muted-foreground">von 100 Punkten</p>
      <Progress
        value={score}
        className="h-3"
        aria-label={`Integritäts-Score: ${score.toFixed(1)} von 100`}
      />
      <Badge
        variant={score >= 95 ? "default" : score >= 80 ? "secondary" : "destructive"}
        className="mt-1"
      >
        {label}
      </Badge>
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function IntegrityReportPanel() {
  const { data: report, isLoading, error } = useIntegrityReport();
  const [hashCopied, setHashCopied] = useState(false);

  const handleCopyHash = () => {
    if (!report?.root_hash) return;
    navigator.clipboard.writeText(report.root_hash);
    setHashCopied(true);
    setTimeout(() => setHashCopied(false), 2000);
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <AlertCircle className="h-12 w-12 text-destructive mb-4" />
          <h3 className="text-lg font-semibold">
            Bericht nicht verfügbar
          </h3>
          <p className="text-muted-foreground text-sm">
            Der Integritätsbericht konnte nicht geladen werden.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (!report) return null;

  return (
    <div className="space-y-4">
      {/* Score Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            {report.integrity_score >= 95 ? (
              <ShieldCheck className="h-5 w-5 text-green-600" />
            ) : (
              <ShieldAlert className="h-5 w-5 text-yellow-600" />
            )}
            Integritäts-Score
          </CardTitle>
        </CardHeader>
        <CardContent>
          <IntegrityScore score={report.integrity_score} />
        </CardContent>
      </Card>

      {/* Chain Info */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Chain-Informationen</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Total Entries */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              Gesamteinträge
            </span>
            <span className="font-mono text-sm font-medium">
              {report.total_entries.toLocaleString("de-DE")}
            </span>
          </div>

          {/* Verified Entries */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              Verifizierte Einträge
            </span>
            <span className="font-mono text-sm font-medium">
              {report.verified_entries.toLocaleString("de-DE")}
            </span>
          </div>

          {/* Root Hash */}
          <div className="space-y-1">
            <span className="text-sm text-muted-foreground">Root Hash</span>
            <div className="flex items-center gap-2">
              <code className="text-xs font-mono bg-muted px-2 py-1 rounded flex-1 truncate">
                {report.root_hash}
              </code>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0 flex-shrink-0"
                onClick={handleCopyHash}
                aria-label="Root Hash kopieren"
              >
                {hashCopied ? (
                  <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
          </div>

          {/* Last Verified */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              Letzte Verifikation
            </span>
            <span className="text-sm">
              {new Date(report.last_verified).toLocaleString("de-DE")}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Violations */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Verletzungen
            </span>
            <Badge
              variant={
                report.violations.length === 0 ? "default" : "destructive"
              }
            >
              {report.violations.length}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {report.violations.length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-green-600">
              <CheckCircle className="h-4 w-4" />
              Keine Verletzungen erkannt
            </div>
          ) : (
            <ul className="space-y-2">
              {report.violations.map((violation, index) => (
                <li
                  key={index}
                  className="flex items-start gap-2 text-sm text-destructive"
                >
                  <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                  <span>{violation}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
