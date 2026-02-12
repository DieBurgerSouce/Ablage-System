/**
 * Alert Detail Dialog Component
 *
 * Detailansicht eines Alerts mit:
 * - Vollständige Informationen
 * - Aktions-Buttons
 * - Metadaten und Kontext
 * - Zeitliche Informationen
 */

import { format } from "date-fns";
import { de } from "date-fns/locale";
import {
  CheckCircle,
  XCircle,
  ArrowUpRight,
  Calendar,
  User,
  FileText,
  Info,
  type LucideIcon,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

import type {
  Alert,
  AlertCategory,
  AlertSeverity,
  AlertStatus,
} from "../api/alerts-api";

interface CategoryConfig {
  label: string;
  icon: LucideIcon;
  color: string;
}

interface SeverityConfig {
  label: string;
  color: string;
  bgColor: string;
}

interface StatusConfig {
  label: string;
  color: string;
  icon: LucideIcon;
}

interface AlertDetailDialogProps {
  alert: Alert | null;
  onClose: () => void;
  onAcknowledge: (id: string) => void;
  onDismiss: (id: string) => void;
  onResolve: (id: string) => void;
  categoryConfig: Record<AlertCategory, CategoryConfig>;
  severityConfig: Record<AlertSeverity, SeverityConfig>;
  statusConfig: Record<AlertStatus, StatusConfig>;
}

export function AlertDetailDialog({
  alert,
  onClose,
  onAcknowledge,
  onDismiss,
  onResolve,
  categoryConfig,
  severityConfig,
  statusConfig,
}: AlertDetailDialogProps) {
  if (!alert) return null;

  const category = categoryConfig[alert.category];
  const severity = severityConfig[alert.severity];
  const status = statusConfig[alert.status];

  const CategoryIcon = category?.icon;
  const StatusIcon = status?.icon;

  const isActive = ["new", "acknowledged", "in_progress", "escalated"].includes(
    alert.status
  );

  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return "-";
    return format(new Date(dateStr), "dd.MM.yyyy HH:mm", { locale: de });
  };

  const handleAcknowledge = () => {
    onAcknowledge(alert.id);
    onClose();
  };

  const handleDismiss = () => {
    onDismiss(alert.id);
    onClose();
  };

  const handleResolve = () => {
    onResolve(alert.id);
    onClose();
  };

  return (
    <Dialog open={!!alert} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <div className="flex items-start gap-4">
            <div className={`rounded-full p-3 ${severity.bgColor}`}>
              {CategoryIcon && (
                <CategoryIcon className={`h-6 w-6 ${category.color}`} />
              )}
            </div>
            <div className="flex-1">
              <DialogTitle className="text-xl">{alert.title}</DialogTitle>
              <DialogDescription className="mt-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline" className={category.color}>
                    {category.label}
                  </Badge>
                  <Badge
                    variant="outline"
                    className={`${severity.color} border-current`}
                  >
                    {severity.label}
                  </Badge>
                  <div className="flex items-center gap-1">
                    {StatusIcon && (
                      <StatusIcon className={`h-4 w-4 ${status.color}`} />
                    )}
                    <span className={status.color}>{status.label}</span>
                  </div>
                </div>
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Message */}
          <div className="bg-muted/50 rounded-lg p-4">
            <p className="text-sm whitespace-pre-wrap">{alert.message}</p>
          </div>

          {/* Details Grid */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-muted-foreground">
                <Info className="h-4 w-4" />
                <span>Alert-Code</span>
              </div>
              <p className="font-mono">{alert.alert_code}</p>
            </div>

            <div className="space-y-1">
              <div className="flex items-center gap-2 text-muted-foreground">
                <Calendar className="h-4 w-4" />
                <span>Erstellt</span>
              </div>
              <p>{formatDateTime(alert.created_at)}</p>
            </div>

            {alert.source_type && (
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <FileText className="h-4 w-4" />
                  <span>Quelle</span>
                </div>
                <p>{alert.source_type}</p>
              </div>
            )}

            {alert.acknowledged_at && (
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <CheckCircle className="h-4 w-4" />
                  <span>Bestätigt</span>
                </div>
                <p>{formatDateTime(alert.acknowledged_at)}</p>
              </div>
            )}

            {alert.resolved_at && (
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>Gelöst</span>
                </div>
                <p>{formatDateTime(alert.resolved_at)}</p>
              </div>
            )}

            {alert.escalation_level > 0 && (
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <ArrowUpRight className="h-4 w-4 text-orange-500" />
                  <span>Eskalationsstufe</span>
                </div>
                <p className="text-orange-500">Stufe {alert.escalation_level}</p>
              </div>
            )}
          </div>

          {/* Resolution Note */}
          {alert.resolution_note && (
            <>
              <Separator />
              <div className="space-y-2">
                <h4 className="text-sm font-medium">Loesungsnotiz</h4>
                <p className="text-sm text-muted-foreground bg-muted/50 rounded-lg p-3">
                  {alert.resolution_note}
                </p>
              </div>
            </>
          )}

          {/* Context / Metadata */}
          {Object.keys(alert.context || {}).length > 0 && (
            <>
              <Separator />
              <div className="space-y-2">
                <h4 className="text-sm font-medium">Zusätzliche Informationen</h4>
                <div className="bg-muted/50 rounded-lg p-3 space-y-2">
                  {Object.entries(alert.context).map(([key, value]) => (
                    <div key={key} className="flex justify-between text-sm">
                      <span className="text-muted-foreground capitalize">
                        {key.replace(/_/g, " ")}
                      </span>
                      <span className="font-medium">{String(value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* Links */}
          <div className="flex flex-wrap gap-2">
            {alert.document_id && (
              <Button variant="outline" size="sm" asChild>
                <a
                  href={`/documents/${alert.document_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <FileText className="mr-2 h-4 w-4" />
                  Dokument öffnen
                </a>
              </Button>
            )}
            {alert.entity_id && (
              <Button variant="outline" size="sm" asChild>
                <a
                  href={`/entities/${alert.entity_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <User className="mr-2 h-4 w-4" />
                  Geschäftspartner anzeigen
                </a>
              </Button>
            )}
          </div>
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          {isActive && (
            <>
              {alert.status === "new" && (
                <Button variant="outline" onClick={handleAcknowledge}>
                  <CheckCircle className="mr-2 h-4 w-4" />
                  Bestätigen
                </Button>
              )}
              <Button variant="outline" onClick={handleDismiss}>
                <XCircle className="mr-2 h-4 w-4" />
                Verwerfen
              </Button>
              <Button onClick={handleResolve}>
                <CheckCircle className="mr-2 h-4 w-4" />
                Als gelöst markieren
              </Button>
            </>
          )}
          {!isActive && (
            <Button variant="outline" onClick={onClose}>
              Schließen
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
