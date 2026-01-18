/**
 * Shipment Detail Component
 *
 * Detailansicht einer Sendung mit Timeline der Tracking-Events.
 * Zeigt alle Sendungsinformationen und Verlauf.
 */

import { Link } from '@tanstack/react-router';
import {
  ArrowLeft,
  ExternalLink,
  RefreshCw,
  Trash2,
  Package,
  Truck,
  MapPin,
  Calendar,
  Clock,
  Weight,
  FileText,
  Euro,
  Building,
  CheckCircle,
  AlertTriangle,
  Tag,
  RotateCcw,
  HelpCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { CarrierIcon, CarrierBadge } from './CarrierIcon';
import { STATUS_STYLES, DIRECTION_STYLES, UI_LABELS } from '../types/shipment-types';
import type { ShipmentResponse, ShipmentEventResponse, ShipmentStatus } from '../types/shipment-types';

// ==================== Types ====================

interface ShipmentDetailProps {
  shipment: ShipmentResponse;
  isLoading?: boolean;
  onRefresh?: () => void;
  onDelete?: () => void;
  isRefreshing?: boolean;
  className?: string;
}

// ==================== Main Component ====================

export function ShipmentDetail({
  shipment,
  isLoading = false,
  onRefresh,
  onDelete,
  isRefreshing = false,
  className,
}: ShipmentDetailProps) {
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

  const formatCurrency = (amount: number | null, currency: string) => {
    if (amount === null) return null;
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: currency,
    }).format(amount);
  };

  if (isLoading) {
    return <ShipmentDetailSkeleton />;
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/sendungen">
              <ArrowLeft className="h-5 w-5" />
            </Link>
          </Button>
          <div>
            <h1 className="text-2xl font-bold font-mono">{shipment.trackingNumber}</h1>
            <div className="flex items-center gap-2 mt-1">
              <CarrierBadge carrier={shipment.carrier} />
              <Badge variant={directionStyle.variant}>{directionStyle.label}</Badge>
              <Badge variant={statusStyle.variant}>{statusStyle.label}</Badge>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onRefresh && (
            <Button variant="outline" onClick={onRefresh} disabled={isRefreshing}>
              <RefreshCw className={cn('h-4 w-4 mr-2', isRefreshing && 'animate-spin')} />
              {UI_LABELS.actionRefresh}
            </Button>
          )}
          {shipment.trackingUrl && (
            <Button variant="outline" asChild>
              <a href={shipment.trackingUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4 mr-2" />
                {UI_LABELS.actionExternalTracking}
              </a>
            </Button>
          )}
          {onDelete && (
            <Button variant="destructive" onClick={onDelete}>
              <Trash2 className="h-4 w-4 mr-2" />
              {UI_LABELS.actionDelete}
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Info */}
        <div className="lg:col-span-2 space-y-6">
          {/* Status Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <StatusIcon status={shipment.status} className="h-5 w-5" />
                Status
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-4">
                <Badge variant={statusStyle.variant} className="text-base px-3 py-1">
                  {statusStyle.label}
                </Badge>
                {shipment.statusDescription && (
                  <span className="text-muted-foreground">{shipment.statusDescription}</span>
                )}
              </div>

              {/* Progress Bar */}
              <ShipmentProgress status={shipment.status} />

              {/* Exception Warning */}
              {shipment.status === 'exception' && (
                <div className="flex items-center gap-2 p-3 rounded-md bg-destructive/10 text-destructive">
                  <AlertTriangle className="h-5 w-5 shrink-0" />
                  <span>Es gibt ein Problem mit dieser Sendung. Bitte prüfen Sie die Details beim Carrier.</span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Timeline */}
          <Card>
            <CardHeader>
              <CardTitle>{UI_LABELS.timelineTitle}</CardTitle>
              <CardDescription>
                {shipment.events.length} Events
                {shipment.lastTrackingUpdate && (
                  <> · Letzte Aktualisierung: {formatDateTime(shipment.lastTrackingUpdate)}</>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {shipment.events.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Package className="h-12 w-12 mx-auto mb-2 opacity-50" />
                  <p>{UI_LABELS.timelineEmpty}</p>
                </div>
              ) : (
                <ShipmentTimeline events={shipment.events} />
              )}
            </CardContent>
          </Card>
        </div>

        {/* Sidebar Info */}
        <div className="space-y-6">
          {/* Carrier & Dates */}
          <Card>
            <CardHeader>
              <CardTitle>{UI_LABELS.detailTitle}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Carrier */}
              <DetailRow
                icon={<Package className="h-4 w-4" />}
                label={UI_LABELS.detailCarrier}
              >
                <CarrierIcon carrier={shipment.carrier} size="sm" showLabel />
              </DetailRow>

              <Separator />

              {/* Origin */}
              {shipment.origin && (
                <DetailRow
                  icon={<MapPin className="h-4 w-4" />}
                  label={UI_LABELS.detailOrigin}
                >
                  {shipment.origin}
                </DetailRow>
              )}

              {/* Destination */}
              {shipment.destination && (
                <DetailRow
                  icon={<MapPin className="h-4 w-4" />}
                  label={UI_LABELS.detailDestination}
                >
                  {shipment.destination}
                </DetailRow>
              )}

              {(shipment.origin || shipment.destination) && <Separator />}

              {/* Estimated Delivery */}
              {shipment.estimatedDelivery && (
                <DetailRow
                  icon={<Calendar className="h-4 w-4" />}
                  label={UI_LABELS.detailEstimatedDelivery}
                >
                  {formatDate(shipment.estimatedDelivery)}
                </DetailRow>
              )}

              {/* Actual Delivery */}
              {shipment.actualDelivery && (
                <DetailRow
                  icon={<CheckCircle className="h-4 w-4 text-green-600" />}
                  label={UI_LABELS.detailActualDelivery}
                >
                  <span className="text-green-600 font-medium">
                    {formatDate(shipment.actualDelivery)}
                  </span>
                </DetailRow>
              )}

              <Separator />

              {/* Weight */}
              {shipment.weightKg && (
                <DetailRow
                  icon={<Weight className="h-4 w-4" />}
                  label={UI_LABELS.detailWeight}
                >
                  {shipment.weightKg.toFixed(2)} kg
                </DetailRow>
              )}

              {/* Service Type */}
              {shipment.serviceType && (
                <DetailRow
                  icon={<Truck className="h-4 w-4" />}
                  label={UI_LABELS.detailServiceType}
                >
                  {shipment.serviceType}
                </DetailRow>
              )}

              {/* Shipping Cost */}
              {shipment.shippingCost !== null && (
                <DetailRow
                  icon={<Euro className="h-4 w-4" />}
                  label={UI_LABELS.detailShippingCost}
                >
                  {formatCurrency(shipment.shippingCost, shipment.currency)}
                </DetailRow>
              )}
            </CardContent>
          </Card>

          {/* Reference & Notes */}
          {(shipment.reference || shipment.notes) && (
            <Card>
              <CardHeader>
                <CardTitle>Zusatzinformationen</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {shipment.reference && (
                  <DetailRow
                    icon={<FileText className="h-4 w-4" />}
                    label={UI_LABELS.detailReference}
                  >
                    {shipment.reference}
                  </DetailRow>
                )}
                {shipment.notes && (
                  <DetailRow
                    icon={<FileText className="h-4 w-4" />}
                    label={UI_LABELS.detailNotes}
                  >
                    {shipment.notes}
                  </DetailRow>
                )}
              </CardContent>
            </Card>
          )}

          {/* Linked Entity */}
          {shipment.entityId && (
            <Card>
              <CardHeader>
                <CardTitle>Verknüpfungen</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <DetailRow
                  icon={<Building className="h-4 w-4" />}
                  label="Geschäftspartner"
                >
                  <Link
                    to="/kunden/$entityId"
                    params={{ entityId: shipment.entityId }}
                    className="text-primary hover:underline"
                  >
                    Details anzeigen
                  </Link>
                </DetailRow>
                {shipment.documentId && (
                  <DetailRow
                    icon={<FileText className="h-4 w-4" />}
                    label="Dokument"
                  >
                    <Link
                      to="/documents/$documentId"
                      params={{ documentId: shipment.documentId }}
                      className="text-primary hover:underline"
                    >
                      Dokument anzeigen
                    </Link>
                  </DetailRow>
                )}
              </CardContent>
            </Card>
          )}

          {/* Metadata */}
          <Card>
            <CardHeader>
              <CardTitle>Metadaten</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <DetailRow
                icon={<Clock className="h-4 w-4" />}
                label={UI_LABELS.detailCreatedAt}
              >
                {formatDateTime(shipment.createdAt)}
              </DetailRow>
              <DetailRow
                icon={<Clock className="h-4 w-4" />}
                label={UI_LABELS.detailUpdatedAt}
              >
                {formatDateTime(shipment.updatedAt)}
              </DetailRow>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ==================== Sub-Components ====================

interface DetailRowProps {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}

function DetailRow({ icon, label, children }: DetailRowProps) {
  return (
    <div className="flex items-start gap-3">
      <div className="text-muted-foreground mt-0.5">{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-muted-foreground">{label}</p>
        <div className="font-medium">{children}</div>
      </div>
    </div>
  );
}

// ==================== Status Icon ====================

interface StatusIconProps {
  status: ShipmentStatus;
  className?: string;
}

function StatusIcon({ status, className }: StatusIconProps) {
  const iconClass = cn('h-5 w-5', className);

  switch (status) {
    case 'label_created':
      return <Tag className={cn(iconClass, 'text-gray-500')} />;
    case 'picked_up':
      return <Package className={cn(iconClass, 'text-blue-500')} />;
    case 'in_transit':
      return <Truck className={cn(iconClass, 'text-blue-600')} />;
    case 'out_for_delivery':
      return <MapPin className={cn(iconClass, 'text-amber-500')} />;
    case 'delivered':
      return <CheckCircle className={cn(iconClass, 'text-green-600')} />;
    case 'exception':
      return <AlertTriangle className={cn(iconClass, 'text-red-500')} />;
    case 'returned':
      return <RotateCcw className={cn(iconClass, 'text-orange-500')} />;
    default:
      return <HelpCircle className={cn(iconClass, 'text-gray-400')} />;
  }
}

// ==================== Progress Bar ====================

interface ShipmentProgressProps {
  status: ShipmentStatus;
}

function ShipmentProgress({ status }: ShipmentProgressProps) {
  const steps = [
    { key: 'label_created', label: 'Label erstellt' },
    { key: 'picked_up', label: 'Abgeholt' },
    { key: 'in_transit', label: 'Unterwegs' },
    { key: 'out_for_delivery', label: 'Zustellung' },
    { key: 'delivered', label: 'Zugestellt' },
  ];

  const statusOrder: Record<string, number> = {
    label_created: 0,
    picked_up: 1,
    in_transit: 2,
    out_for_delivery: 3,
    delivered: 4,
    exception: -1,
    returned: -1,
    unknown: -1,
  };

  const currentStep = statusOrder[status] ?? -1;
  const isException = status === 'exception' || status === 'returned';

  return (
    <div className="flex items-center gap-1">
      {steps.map((step, index) => {
        const isActive = index <= currentStep;
        const isCurrent = index === currentStep;

        return (
          <div key={step.key} className="flex items-center flex-1">
            <div
              className={cn(
                'flex items-center justify-center w-8 h-8 rounded-full text-xs font-medium transition-colors',
                isActive
                  ? isException
                    ? 'bg-red-100 text-red-700'
                    : isCurrent
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-green-100 text-green-700'
                  : 'bg-muted text-muted-foreground'
              )}
            >
              {isActive && !isException ? (
                <CheckCircle className="h-4 w-4" />
              ) : (
                index + 1
              )}
            </div>
            {index < steps.length - 1 && (
              <div
                className={cn(
                  'flex-1 h-1 mx-1',
                  index < currentStep
                    ? isException
                      ? 'bg-red-200'
                      : 'bg-green-200'
                    : 'bg-muted'
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ==================== Timeline ====================

interface ShipmentTimelineProps {
  events: ShipmentEventResponse[];
}

function ShipmentTimeline({ events }: ShipmentTimelineProps) {
  // Sort events by timestamp descending (newest first)
  const sortedEvents = [...events].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  const formatEventTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return {
      date: date.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      }),
      time: date.toLocaleTimeString('de-DE', {
        hour: '2-digit',
        minute: '2-digit',
      }),
    };
  };

  return (
    <div className="relative pl-6">
      {/* Timeline Line */}
      <div className="absolute left-2 top-2 bottom-2 w-0.5 bg-border" />

      <div className="space-y-6">
        {sortedEvents.map((event, index) => {
          const { date, time } = formatEventTime(event.timestamp);
          const isFirst = index === 0;

          return (
            <div key={event.id} className="relative">
              {/* Timeline Dot */}
              <div
                className={cn(
                  'absolute -left-4 top-1 w-4 h-4 rounded-full border-2 border-background',
                  isFirst ? 'bg-primary' : 'bg-muted'
                )}
              />

              {/* Event Content */}
              <div className={cn('ml-4', !isFirst && 'opacity-80')}>
                <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                  <span>{date}</span>
                  <span>·</span>
                  <span>{time}</span>
                  {event.location && (
                    <>
                      <span>·</span>
                      <span className="flex items-center gap-1">
                        <MapPin className="h-3 w-3" />
                        {event.location}
                        {event.postalCode && ` (${event.postalCode})`}
                      </span>
                    </>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <StatusIcon status={event.status} className="h-4 w-4" />
                  <span className={cn('font-medium', isFirst && 'text-primary')}>
                    {STATUS_STYLES[event.status]?.label || event.status}
                  </span>
                </div>
                {event.description && (
                  <p className="text-sm text-muted-foreground mt-1">{event.description}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ==================== Skeleton ====================

function ShipmentDetailSkeleton() {
  return (
    <div className="space-y-6">
      {/* Header Skeleton */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Skeleton className="h-10 w-10 rounded" />
          <div>
            <Skeleton className="h-8 w-64 mb-2" />
            <div className="flex gap-2">
              <Skeleton className="h-6 w-16" />
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-6 w-24" />
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-10 w-32" />
          <Skeleton className="h-10 w-40" />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Skeleton className="h-48 rounded-lg" />
          <Skeleton className="h-96 rounded-lg" />
        </div>
        <div className="space-y-6">
          <Skeleton className="h-80 rounded-lg" />
          <Skeleton className="h-40 rounded-lg" />
        </div>
      </div>
    </div>
  );
}

export default ShipmentDetail;
