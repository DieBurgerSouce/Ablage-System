/**
 * Shipment List Component
 *
 * Hauptliste für Sendungsverfolgung mit Tabelle, Filtern und Pagination.
 * Unterstützt alle 7 Carrier und Status-Filter.
 */

import { useState, useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import {
  ExternalLink,
  RefreshCw,
  MoreHorizontal,
  Eye,
  Trash2,
  Filter,
  X,
  Package,
  Truck,
  CheckCircle,
  AlertTriangle,
  Plus,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { CarrierIcon, getCarrierOptions } from './CarrierIcon';
import { ShipmentSummaryCard } from './ShipmentTrackingCard';
import {
  UI_LABELS,
  STATUS_STYLES,
  DIRECTION_STYLES,
} from '../types/shipment-types';
import type {
  ShipmentResponse,
  ShipmentFilter,
  ShipmentStatus,
  ShipmentDirection,
  CarrierId,
  ShipmentSummaryResponse,
} from '../types/shipment-types';

// ==================== Types ====================

interface ShipmentListProps {
  shipments: ShipmentResponse[];
  pagination: {
    total: number;
    page: number;
    perPage: number;
    pages: number;
  } | null;
  summary?: ShipmentSummaryResponse | null;
  isLoading?: boolean;
  isFetching?: boolean;
  filter: Partial<ShipmentFilter>;
  onFilterChange: (filter: Partial<ShipmentFilter>) => void;
  onRefresh?: (shipmentId: string) => void;
  onRefreshAll?: () => void;
  onDelete?: (shipmentId: string) => void;
  isRefreshing?: boolean;
  isRefreshingAll?: boolean;
  className?: string;
}

// ==================== Status Options ====================

const STATUS_OPTIONS: Array<{ value: ShipmentStatus | 'all'; label: string }> = [
  { value: 'all', label: UI_LABELS.filterAll },
  { value: 'label_created', label: UI_LABELS.statusLabelCreated },
  { value: 'picked_up', label: UI_LABELS.statusPickedUp },
  { value: 'in_transit', label: UI_LABELS.statusInTransit },
  { value: 'out_for_delivery', label: UI_LABELS.statusOutForDelivery },
  { value: 'delivered', label: UI_LABELS.statusDelivered },
  { value: 'exception', label: UI_LABELS.statusException },
  { value: 'returned', label: UI_LABELS.statusReturned },
];

const DIRECTION_OPTIONS: Array<{ value: ShipmentDirection | 'all'; label: string }> = [
  { value: 'all', label: UI_LABELS.filterAll },
  { value: 'inbound', label: UI_LABELS.directionInbound },
  { value: 'outbound', label: UI_LABELS.directionOutbound },
  { value: 'return', label: UI_LABELS.directionReturn },
];

// ==================== Main Component ====================

export function ShipmentList({
  shipments,
  pagination,
  summary,
  isLoading = false,
  isFetching = false,
  filter,
  onFilterChange,
  onRefresh,
  onRefreshAll,
  onDelete,
  isRefreshing = false,
  isRefreshingAll = false,
  className,
}: ShipmentListProps) {
  const [deleteShipmentId, setDeleteShipmentId] = useState<string | null>(null);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);

  const carrierOptions = useMemo(() => {
    return [{ value: 'all' as const, label: UI_LABELS.filterAll }, ...getCarrierOptions()];
  }, []);

  const hasActiveFilters = filter.status || filter.carrier || filter.direction;

  const handleRefresh = async (shipmentId: string) => {
    if (onRefresh) {
      setRefreshingId(shipmentId);
      try {
        await onRefresh(shipmentId);
      } finally {
        setRefreshingId(null);
      }
    }
  };

  const handleDelete = () => {
    if (deleteShipmentId && onDelete) {
      onDelete(deleteShipmentId);
      setDeleteShipmentId(null);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  };

  if (isLoading) {
    return <ShipmentListSkeleton />;
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <ShipmentSummaryCard
            title={UI_LABELS.summaryTotal}
            value={summary.total}
            icon={<Package className="h-5 w-5" />}
            variant="default"
          />
          <ShipmentSummaryCard
            title={UI_LABELS.summaryPending}
            value={summary.pendingDelivery}
            icon={<Truck className="h-5 w-5" />}
            variant="muted"
          />
          <ShipmentSummaryCard
            title={UI_LABELS.summaryDeliveredToday}
            value={summary.deliveredToday}
            icon={<CheckCircle className="h-5 w-5" />}
            variant="success"
          />
          <ShipmentSummaryCard
            title={UI_LABELS.summaryExceptions}
            value={summary.exceptions}
            icon={<AlertTriangle className="h-5 w-5" />}
            variant={summary.exceptions > 0 ? 'warning' : 'muted'}
          />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Filter:</span>
        </div>

        {/* Status Filter */}
        <Select
          value={filter.status || 'all'}
          onValueChange={(value) =>
            onFilterChange({
              ...filter,
              status: value === 'all' ? undefined : (value as ShipmentStatus),
              page: 1,
            })
          }
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder={UI_LABELS.filterStatus} />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Carrier Filter */}
        <Select
          value={filter.carrier || 'all'}
          onValueChange={(value) =>
            onFilterChange({
              ...filter,
              carrier: value === 'all' ? undefined : (value as CarrierId),
              page: 1,
            })
          }
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder={UI_LABELS.filterCarrier} />
          </SelectTrigger>
          <SelectContent>
            {carrierOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Direction Filter */}
        <Select
          value={filter.direction || 'all'}
          onValueChange={(value) =>
            onFilterChange({
              ...filter,
              direction: value === 'all' ? undefined : (value as ShipmentDirection),
              page: 1,
            })
          }
        >
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder={UI_LABELS.filterDirection} />
          </SelectTrigger>
          <SelectContent>
            {DIRECTION_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Clear Filters */}
        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              onFilterChange({
                page: 1,
                perPage: filter.perPage,
              })
            }
          >
            <X className="h-4 w-4 mr-1" />
            {UI_LABELS.filterReset}
          </Button>
        )}

        {/* Refresh All */}
        <div className="flex-1" />
        {onRefreshAll && (
          <Button
            variant="outline"
            size="sm"
            onClick={onRefreshAll}
            disabled={isRefreshingAll}
          >
            <RefreshCw
              className={cn('h-4 w-4 mr-2', isRefreshingAll && 'animate-spin')}
            />
            Alle aktualisieren
          </Button>
        )}

        {/* Add Shipment */}
        <Button size="sm" asChild>
          <Link to="/sendungen/neu">
            <Plus className="h-4 w-4 mr-2" />
            {UI_LABELS.actionCreate}
          </Link>
        </Button>
      </div>

      {/* Table */}
      <div className="border rounded-lg">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[200px]">{UI_LABELS.tableTrackingNumber}</TableHead>
              <TableHead className="w-[120px]">{UI_LABELS.tableCarrier}</TableHead>
              <TableHead className="w-[120px]">{UI_LABELS.tableStatus}</TableHead>
              <TableHead className="w-[100px]">{UI_LABELS.tableDirection}</TableHead>
              <TableHead>{UI_LABELS.tableDestination}</TableHead>
              <TableHead className="w-[120px]">{UI_LABELS.tableEstimatedDelivery}</TableHead>
              <TableHead className="w-[80px] text-right">{UI_LABELS.tableActions}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shipments.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="h-32 text-center">
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <Package className="h-10 w-10 opacity-50" />
                    <p className="font-medium">{UI_LABELS.emptyTitle}</p>
                    <p className="text-sm">{UI_LABELS.emptyDescription}</p>
                    <Button variant="outline" size="sm" asChild className="mt-2">
                      <Link to="/sendungen/neu">
                        <Plus className="h-4 w-4 mr-2" />
                        {UI_LABELS.emptyAction}
                      </Link>
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              shipments.map((shipment) => {
                const statusStyle = STATUS_STYLES[shipment.status] || STATUS_STYLES.unknown;
                const directionStyle =
                  DIRECTION_STYLES[shipment.direction] || DIRECTION_STYLES.inbound;

                return (
                  <TableRow
                    key={shipment.id}
                    className={cn(isFetching && 'opacity-50')}
                  >
                    <TableCell>
                      <Link
                        to="/sendungen/$shipmentId"
                        params={{ shipmentId: shipment.id }}
                        className="font-mono text-sm hover:underline"
                      >
                        {shipment.trackingNumber}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <CarrierIcon carrier={shipment.carrier} size="sm" />
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusStyle.variant}>{statusStyle.label}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={directionStyle.variant}>{directionStyle.label}</Badge>
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate">
                      {shipment.destination || '-'}
                    </TableCell>
                    <TableCell>{formatDate(shipment.estimatedDelivery)}</TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem asChild>
                            <Link
                              to="/sendungen/$shipmentId"
                              params={{ shipmentId: shipment.id }}
                            >
                              <Eye className="h-4 w-4 mr-2" />
                              {UI_LABELS.actionDetails}
                            </Link>
                          </DropdownMenuItem>
                          {shipment.trackingUrl && (
                            <DropdownMenuItem asChild>
                              <a
                                href={shipment.trackingUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                <ExternalLink className="h-4 w-4 mr-2" />
                                {UI_LABELS.actionExternalTracking}
                              </a>
                            </DropdownMenuItem>
                          )}
                          {onRefresh && (
                            <DropdownMenuItem
                              onClick={() => handleRefresh(shipment.id)}
                              disabled={refreshingId === shipment.id || isRefreshing}
                            >
                              <RefreshCw
                                className={cn(
                                  'h-4 w-4 mr-2',
                                  refreshingId === shipment.id && 'animate-spin'
                                )}
                              />
                              {UI_LABELS.actionRefresh}
                            </DropdownMenuItem>
                          )}
                          {onDelete && (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() => setDeleteShipmentId(shipment.id)}
                                className="text-destructive focus:text-destructive"
                              >
                                <Trash2 className="h-4 w-4 mr-2" />
                                {UI_LABELS.actionDelete}
                              </DropdownMenuItem>
                            </>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {pagination && pagination.pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Seite {pagination.page} von {pagination.pages} ({pagination.total} Sendungen)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onFilterChange({ ...filter, page: pagination.page - 1 })}
              disabled={pagination.page <= 1}
            >
              Zurück
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onFilterChange({ ...filter, page: pagination.page + 1 })}
              disabled={pagination.page >= pagination.pages}
            >
              Weiter
            </Button>
          </div>
        </div>
      )}

      {/* Delete Dialog */}
      <AlertDialog open={!!deleteShipmentId} onOpenChange={() => setDeleteShipmentId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Sendung löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie diese Sendung wirklich löschen? Diese Aktion kann nicht
              rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive">
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ==================== Skeleton ====================

function ShipmentListSkeleton() {
  return (
    <div className="space-y-6">
      {/* Summary Cards Skeleton */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-lg" />
        ))}
      </div>

      {/* Filters Skeleton */}
      <div className="flex gap-4">
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-10 w-40" />
        <Skeleton className="h-10 w-40" />
        <Skeleton className="h-10 w-32" />
      </div>

      {/* Table Skeleton */}
      <div className="border rounded-lg">
        <div className="p-4 space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex gap-4">
              <Skeleton className="h-6 w-40" />
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-6 w-24" />
              <Skeleton className="h-6 w-24" />
              <Skeleton className="h-6 flex-1" />
              <Skeleton className="h-6 w-24" />
              <Skeleton className="h-6 w-8" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default ShipmentList;
