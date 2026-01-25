/**
 * Alert Card Component
 *
 * Einzelne Alert-Karte mit:
 * - Kategorie-Icon und Farbe
 * - Schweregrad-Badge
 * - Status-Anzeige
 * - Quick-Actions
 */

import { formatDistanceToNow } from "date-fns";
import { de } from "date-fns/locale";
import {
  CheckCircle,
  XCircle,
  MoreVertical,
  ExternalLink,
  type LucideIcon,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

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

interface AlertCardProps {
  alert: Alert;
  isSelected: boolean;
  onToggleSelect: () => void;
  onClick: () => void;
  onAcknowledge: () => void;
  onDismiss: () => void;
  onResolve: () => void;
  categoryConfig: Record<AlertCategory, CategoryConfig>;
  severityConfig: Record<AlertSeverity, SeverityConfig>;
  statusConfig: Record<AlertStatus, StatusConfig>;
}

export function AlertCard({
  alert,
  isSelected,
  onToggleSelect,
  onClick,
  onAcknowledge,
  onDismiss,
  onResolve,
  categoryConfig,
  severityConfig,
  statusConfig,
}: AlertCardProps) {
  const category = categoryConfig[alert.category];
  const severity = severityConfig[alert.severity];
  const status = statusConfig[alert.status];

  const CategoryIcon = category?.icon;
  const StatusIcon = status?.icon;

  const isActive = ["new", "acknowledged", "in_progress", "escalated"].includes(
    alert.status
  );

  const createdAgo = formatDistanceToNow(new Date(alert.created_at), {
    addSuffix: true,
    locale: de,
  });

  return (
    <Card
      className={`transition-all hover:shadow-md cursor-pointer ${
        isSelected ? "ring-2 ring-primary" : ""
      } ${!isActive ? "opacity-60" : ""} ${
        alert.severity === "critical" ? "border-red-500" : ""
      }`}
    >
      <CardContent className="p-4">
        <div className="flex items-start gap-4">
          {/* Checkbox */}
          <div className="pt-1" onClick={(e) => e.stopPropagation()}>
            <Checkbox
              checked={isSelected}
              onCheckedChange={onToggleSelect}
              aria-label={`Alert ${alert.title} auswaehlen`}
            />
          </div>

          {/* Category Icon */}
          <div
            className={`rounded-full p-2 ${severity.bgColor}`}
            onClick={onClick}
          >
            {CategoryIcon && (
              <CategoryIcon className={`h-5 w-5 ${category.color}`} />
            )}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0" onClick={onClick}>
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <h3 className="font-medium leading-tight truncate">
                  {alert.title}
                </h3>
                <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                  {alert.message}
                </p>
              </div>

              {/* Badges */}
              <div className="flex flex-col items-end gap-1 shrink-0">
                <Badge
                  variant="outline"
                  className={`${severity.color} border-current`}
                >
                  {severity.label}
                </Badge>
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  {StatusIcon && <StatusIcon className={`h-3 w-3 ${status.color}`} />}
                  <span>{status.label}</span>
                </div>
              </div>
            </div>

            {/* Meta */}
            <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
              <span className={category.color}>{category.label}</span>
              <span>•</span>
              <span>{alert.alert_code}</span>
              <span>•</span>
              <span>{createdAgo}</span>
              {alert.escalation_level > 0 && (
                <>
                  <span>•</span>
                  <span className="text-orange-500">
                    Eskaliert (Stufe {alert.escalation_level})
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Quick Actions */}
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            {isActive && (
              <>
                {alert.status === "new" && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={onAcknowledge}
                    title="Als gelesen markieren"
                  >
                    <CheckCircle className="h-4 w-4" />
                  </Button>
                )}

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {alert.status === "new" && (
                      <DropdownMenuItem onClick={onAcknowledge}>
                        <CheckCircle className="mr-2 h-4 w-4" />
                        Bestaetigen
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem onClick={onResolve}>
                      <CheckCircle className="mr-2 h-4 w-4 text-green-500" />
                      Als geloest markieren
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={onDismiss}>
                      <XCircle className="mr-2 h-4 w-4" />
                      Verwerfen
                    </DropdownMenuItem>
                    {alert.document_id && (
                      <DropdownMenuItem asChild>
                        <a
                          href={`/documents/${alert.document_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <ExternalLink className="mr-2 h-4 w-4" />
                          Dokument oeffnen
                        </a>
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
