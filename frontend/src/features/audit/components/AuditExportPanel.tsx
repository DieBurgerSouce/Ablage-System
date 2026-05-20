/**
 * AuditExportPanel - Export-Steuerung
 *
 * Ermöglicht den Export der Audit-Chain als JSON
 * mit konfigurierbarem Zeitraum.
 */

import { useState } from "react";
import {
  Download,
  FileJson,
  Loader2,
  Calendar,
  CheckCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

import { useExportChain } from "../api/audit-chain-api";

// =============================================================================
// Helpers
// =============================================================================

function getDefaultFromDate(): string {
  const date = new Date();
  date.setDate(date.getDate() - 30);
  return date.toISOString().split("T")[0];
}

function getDefaultToDate(): string {
  return new Date().toISOString().split("T")[0];
}

// =============================================================================
// Main Component
// =============================================================================

export function AuditExportPanel() {
  const [fromDate, setFromDate] = useState(getDefaultFromDate);
  const [toDate, setToDate] = useState(getDefaultToDate);
  const [recentExports, setRecentExports] = useState<
    Array<{ date: string; from: string; to: string }>
  >([]);

  const exportMutation = useExportChain();

  const handleExport = () => {
    exportMutation.mutate(
      {
        fromDate: fromDate ? new Date(fromDate).toISOString() : undefined,
        toDate: toDate ? new Date(toDate).toISOString() : undefined,
      },
      {
        onSuccess: (blob) => {
          // Trigger download
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `audit-chain-${fromDate}_${toDate}.json`;
          link.click();
          URL.revokeObjectURL(url);

          // Track in recent exports
          setRecentExports((prev) => [
            {
              date: new Date().toLocaleString("de-DE"),
              from: fromDate,
              to: toDate,
            },
            ...prev.slice(0, 4),
          ]);
        },
      }
    );
  };

  return (
    <div className="space-y-4">
      {/* Export Controls */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Download className="h-5 w-5" />
            Audit-Chain exportieren
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Exportieren Sie die Audit-Chain inklusive aller Einträge und
            Merkle Tree als JSON-Datei für externe Prüfungen.
          </p>

          {/* Date Range */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label
                htmlFor="export-from"
                className="text-sm font-medium flex items-center gap-1"
              >
                <Calendar className="h-3.5 w-3.5" />
                Von
              </label>
              <Input
                id="export-from"
                type="date"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
                aria-label="Export-Startdatum"
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="export-to"
                className="text-sm font-medium flex items-center gap-1"
              >
                <Calendar className="h-3.5 w-3.5" />
                Bis
              </label>
              <Input
                id="export-to"
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                aria-label="Export-Enddatum"
              />
            </div>
          </div>

          {/* Format Info */}
          <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg">
            <FileJson className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">JSON-Format</p>
              <p className="text-xs text-muted-foreground">
                Audit-Logs, Merkle Tree, Root Hash und Metadaten
              </p>
            </div>
          </div>

          {/* Export Button */}
          <Button
            onClick={handleExport}
            disabled={exportMutation.isPending}
            className="w-full"
          >
            {exportMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Exportiere...
              </>
            ) : (
              <>
                <Download className="mr-2 h-4 w-4" />
                Exportieren
              </>
            )}
          </Button>

          {exportMutation.isError && (
            <p className="text-sm text-destructive">
              Export fehlgeschlagen. Bitte versuchen Sie es erneut.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Recent Exports */}
      {recentExports.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Letzte Exporte</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {recentExports.map((exp, index) => (
                <li
                  key={index}
                  className="flex items-center justify-between text-sm"
                >
                  <div className="flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    <span>
                      {exp.from} bis {exp.to}
                    </span>
                  </div>
                  <Badge variant="outline" className="text-xs">
                    {exp.date}
                  </Badge>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
