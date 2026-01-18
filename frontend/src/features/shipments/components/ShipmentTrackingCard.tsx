/**
 * Shipment Tracking Card Component
 *
 * Kompakte Status-Karte für Sendungsverfolgung.
 * Zeigt Status, Carrier und letzte Aktualisierung.
 */

import { ExternalLink, RefreshCw, Truck, MapPin, Clock, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { CarrierIcon } from './CarrierIcon';
import { STATUS_STYLES, DIRECTION_STYLES, UI_LABELS } from '../types/shipment-types';
import type { ShipmentResponse, ShipmentStatus, ShipmentDirection } from '../types/shipment-types';

interface ShipmentTrackingCardProps {
  shipment: ShipmentResponse;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  compact?: boolean;
  className?: string;
}

export function ShipmentTrackingCard({
  shipment,
  onRefresh,
  isRefreshing = false,
  compact = false,
  className,
}: ShipmentTrackingCardProps) {
  const statusStyle = STATUS_STYLES[shipment.status] || STATUS_STYLES.unknown;
  const directionStyle = DIRECTION_STYLES[shipment.direction] || DIRECTION_STYLES.inbound;

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return null;
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  };

  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return null;
    return new Date(dateStr).toLocaleString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getRelativeTime = (dateStr: string | null) => {
    if (!dateStr) return null;
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Gerade eben';
    if (diffMins < 60) return `vor ${diffMins} Min.`;
    if (diffHours < 24) return `vor ${diffHours} Std.`;
    if (diffDays < 7) return `vor ${diffDays} Tagen`;
    return formatDate(dateStr);
  };

  if (compact) {
    return (
      <div
        className={cn(
          'flex items-center justify-between gap-4 rounded-lg border p-3',
          className
        )}
      >
        <div className="flex items-center gap-3">
          <CarrierIcon carrier={shipment.carrier} size="sm" />
          <div className="min-w-0">
            <p className="text-sm font-mono truncate">{shipment.trackingNumber}</p>
            <p className="text-xs text-muted-foreground">
              {getRelativeTime(shipment.lastTrackingUpdate)}
            </p>
          </div>
        </div>
        <Badge variant={statusStyle.variant}>{statusStyle.label}</Badge>
      </div>
    );
  }

  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <CarrierIcon carrier={shipment.carrier} size="md" showLabel />
            <Badge variant={directionStyle.variant}>{directionStyle.label}</Badge>
          </div>
          <div className="flex items-center gap-2">
            {onRefresh && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={onRefresh}
                      disabled={isRefreshing}
                    >
                      <RefreshCw
                        className={cn('h-4 w-4', isRefreshing && 'animate-spin')}
                      />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{UI_LABELS.actionRefresh}</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
            {shipment.trackingUrl && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="ghost" size="icon" asChild>
                      <a
                        href={shipment.trackingUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{UI_LABELS.actionExternalTracking}</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Tracking Number */}
        <div>
          <p className="text-xs text-muted-foreground mb-1">
            {UI_LABELS.tableTrackingNumber}
          </p>
          <p className="font-mono text-sm font-medium">{shipment.trackingNumber}</p>
        </div>

        {/* Status */}
        <div className="flex items-center gap-3">
          <StatusIcon status={shipment.status} />
          <div className="flex-1 min-w-0">
            <Badge variant={statusStyle.variant} className="mb-1">
              {statusStyle.label}
            </Badge>
            {shipment.statusDescription && (
              <p className="text-xs text-muted-foreground truncate">
                {shipment.statusDescription}
              </p>
            )}
          </div>
        </div>

        {/* Destination & Dates */}
        <div className="grid grid-cols-2 gap-4 text-sm">
          {shipment.destination && (
            <div className="flex items-start gap-2">
              <MapPin className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
              <div>
                <p className="text-xs text-muted-foreground">
                  {UI_LABELS.tableDestination}
                </p>
                <p className="font-medium">{shipment.destination}</p>
              </div>
            </div>
          )}

          {shipment.estimatedDelivery && (
            <div className="flex items-start gap-2">
              <Clock className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
              <div>
                <p className="text-xs text-muted-foreground">
                  {UI_LABELS.tableEstimatedDelivery}
                </p>
                <p className="font-medium">{formatDate(shipment.estimatedDelivery)}</p>
              </div>
            </div>
          )}
        </div>

        {/* Last Update */}
        {shipment.lastTrackingUpdate && (
          <div className="pt-2 border-t text-xs text-muted-foreground">
            Letzte Aktualisierung: {formatDateTime(shipment.lastTrackingUpdate)}
          </div>
        )}

        {/* Exception Warning */}
        {shipment.status === 'exception' && (
          <div className="flex items-center gap-2 p-2 rounded-md bg-destructive/10 text-destructive text-sm">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>Es gibt ein Problem mit dieser Sendung</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ==================== Status Icon ====================

interface StatusIconProps {
  status: ShipmentStatus;
  className?: string;
}

function StatusIcon({ status, className }: StatusIconProps) {
  const iconClasses = cn('h-8 w-8 p-1.5 rounded-full', className);

  switch (status) {
    case 'delivered':
      return (
        <div className={cn(iconClasses, 'bg-green-100 text-green-700')}>
          <Truck className="h-full w-full" />
        </div>
      );
    case 'in_transit':
    case 'out_for_delivery':
      return (
        <div className={cn(iconClasses, 'bg-blue-100 text-blue-700')}>
          <Truck className="h-full w-full" />
        </div>
      );
    case 'exception':
    case 'returned':
      return (
        <div className={cn(iconClasses, 'bg-red-100 text-red-700')}>
          <AlertTriangle className="h-full w-full" />
        </div>
      );
    default:
      return (
        <div className={cn(iconClasses, 'bg-gray-100 text-gray-700')}>
          <Truck className="h-full w-full" />
        </div>
      );
  }
}

// ==================== Summary Card ====================

interface ShipmentSummaryCardProps {
  title: string;
  value: number;
  icon: React.ReactNode;
  variant?: 'default' | 'warning' | 'success' | 'muted';
  className?: string;
}

export function ShipmentSummaryCard({
  title,
  value,
  icon,
  variant = 'default',
  className,
}: ShipmentSummaryCardProps) {
  const variantClasses = {
    default: 'bg-primary/10 text-primary',
    warning: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    success: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    muted: 'bg-muted text-muted-foreground',
  };

  return (
    <Card className={className}>
      <CardContent className="pt-6">
        <div className="flex items-center gap-4">
          <div className={cn('p-3 rounded-lg', variantClasses[variant])}>
            {icon}
          </div>
          <div>
            <p className="text-2xl font-bold">{value}</p>
            <p className="text-sm text-muted-foreground">{title}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default ShipmentTrackingCard;
