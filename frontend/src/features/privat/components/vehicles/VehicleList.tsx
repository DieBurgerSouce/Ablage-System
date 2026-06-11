/**
 * VehicleList - Fahrzeug-Übersicht
 *
 * Liste aller Fahrzeuge mit Verbrauchsstatistiken
 */

import * as React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Plus,
  MoreHorizontal,
  Car,
  Fuel,
  Gauge,
  Euro,
  Edit,
  Trash2,
  Eye,
  Search,
  ChevronLeft,
  ChevronRight,
  Calendar,
} from 'lucide-react';
import type { PrivatVehicleWithStats, VehicleType, FuelType } from '@/types/privat';
import { cn } from '@/lib/utils';

interface VehicleListProps {
  vehicles: PrivatVehicleWithStats[];
  total: number;
  page: number;
  pageSize: number;
  isLoading?: boolean;
  error?: Error | null;
  onPageChange?: (page: number) => void;
  onSelect?: (vehicle: PrivatVehicleWithStats) => void;
  onEdit?: (vehicle: PrivatVehicleWithStats) => void;
  onDelete?: (vehicle: PrivatVehicleWithStats) => void;
  onCreate?: () => void;
  onSearch?: (query: string) => void;
  searchQuery?: string;
  className?: string;
}

const formatCurrency = (amount?: number): string => {
  if (amount === undefined) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
};

const formatDate = (dateStr?: string): string => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

const getVehicleTypeLabel = (type: VehicleType): string => {
  const types: Record<VehicleType, string> = {
    car: 'PKW',
    motorcycle: 'Motorrad',
    truck: 'LKW',
    trailer: 'Anhänger',
    other: 'Sonstiges',
  };
  return types[type];
};

const getVehicleTypeIcon = (type: VehicleType): React.ReactNode => {
  // All use Car icon for now, could be expanded
  return <Car className="h-4 w-4" />;
};

const getFuelTypeLabel = (type?: FuelType): string => {
  if (!type) return '-';
  const types: Record<FuelType, string> = {
    petrol: 'Benzin',
    diesel: 'Diesel',
    electric: 'Elektro',
    hybrid: 'Hybrid',
    lpg: 'LPG',
    other: 'Sonstiges',
  };
  return types[type];
};

const getFuelTypeColor = (type?: FuelType): string => {
  if (!type) return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200';
  const colors: Record<FuelType, string> = {
    petrol: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
    diesel: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
    electric: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    hybrid: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    lpg: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    other: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  };
  return colors[type];
};

export function VehicleList({
  vehicles,
  total,
  page,
  pageSize,
  isLoading,
  error,
  onPageChange,
  onSelect,
  onEdit,
  onDelete,
  onCreate,
  onSearch,
  searchQuery = '',
  className,
}: VehicleListProps) {
  const totalPages = Math.ceil(total / pageSize);

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Fahrzeuge</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Fahrzeuge
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-orange-100 dark:bg-orange-950">
            <Car className="h-6 w-6 text-orange-600 dark:text-orange-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Fahrzeuge</h1>
            <p className="text-muted-foreground">
              {total} {total === 1 ? 'Fahrzeug' : 'Fahrzeuge'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Suchen..."
              value={searchQuery}
              onChange={(e) => onSearch?.(e.target.value)}
              className="pl-8 w-[200px]"
            />
          </div>
          {onCreate && (
            <Button onClick={onCreate}>
              <Plus className="mr-2 h-4 w-4" />
              Neues Fahrzeug
            </Button>
          )}
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      ) : vehicles.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Car className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">Keine Fahrzeuge</h3>
            <p className="text-muted-foreground text-center mb-4">
              Erfassen Sie Ihr erstes Fahrzeug, um Tankbelege und Kosten zu verfolgen.
            </p>
            {onCreate && (
              <Button onClick={onCreate}>
                <Plus className="mr-2 h-4 w-4" />
                Fahrzeug hinzufügen
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {vehicles.map((vehicle) => (
              <VehicleCard
                key={vehicle.id}
                vehicle={vehicle}
                onSelect={onSelect}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <div className="text-sm text-muted-foreground">
                Seite {page + 1} von {totalPages}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onPageChange?.(Math.max(0, page - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                  Zurück
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onPageChange?.(Math.min(totalPages - 1, page + 1))}
                  disabled={page >= totalPages - 1}
                >
                  Weiter
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

interface VehicleCardProps {
  vehicle: PrivatVehicleWithStats;
  onSelect?: (vehicle: PrivatVehicleWithStats) => void;
  onEdit?: (vehicle: PrivatVehicleWithStats) => void;
  onDelete?: (vehicle: PrivatVehicleWithStats) => void;
}

function VehicleCard({ vehicle, onSelect, onEdit, onDelete }: VehicleCardProps) {
  const vehicleName = [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || vehicle.name;

  return (
    <Card
      className={cn(
        'hover:shadow-md transition-shadow',
        onSelect && 'cursor-pointer'
      )}
      onClick={() => onSelect?.(vehicle)}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="secondary">
                {getVehicleTypeLabel(vehicle.vehicleType)}
              </Badge>
              {vehicle.fuelType && (
                <Badge variant="secondary" className={getFuelTypeColor(vehicle.fuelType)}>
                  {getFuelTypeLabel(vehicle.fuelType)}
                </Badge>
              )}
            </div>
            <CardTitle className="text-lg">{vehicleName}</CardTitle>
            {vehicle.licensePlate && (
              <CardDescription className="font-mono">
                {vehicle.licensePlate}
              </CardDescription>
            )}
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onSelect?.(vehicle)}>
                <Eye className="mr-2 h-4 w-4" />
                Details
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onEdit?.(vehicle)}>
                <Edit className="mr-2 h-4 w-4" />
                Bearbeiten
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => onDelete?.(vehicle)}
                className="text-destructive"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Löschen
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardHeader>
      <CardContent>
        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-3">
          {/* Mileage */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <Gauge className="h-4 w-4 text-blue-500" />
            <div>
              <p className="text-xs text-muted-foreground">Kilometerstand</p>
              <p className="font-medium">
                {vehicle.currentMileage?.toLocaleString('de-DE') ?? '-'} km
              </p>
            </div>
          </div>

          {/* Consumption */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <Fuel className="h-4 w-4 text-amber-500" />
            <div>
              <p className="text-xs text-muted-foreground">Verbrauch</p>
              <p className="font-medium">
                {vehicle.averageConsumption?.toFixed(1) ?? '-'} l/100km
              </p>
            </div>
          </div>

          {/* Total Fuel Cost */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <Euro className="h-4 w-4 text-green-500" />
            <div>
              <p className="text-xs text-muted-foreground">Kraftstoffkosten</p>
              <p className="font-medium">{formatCurrency(vehicle.totalFuelCost)}</p>
            </div>
          </div>

          {/* Cost per km */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <Car className="h-4 w-4 text-purple-500" />
            <div>
              <p className="text-xs text-muted-foreground">Kosten/km</p>
              <p className="font-medium">
                {vehicle.costPerKm?.toFixed(2) ?? '-'} EUR
              </p>
            </div>
          </div>
        </div>

        {/* Additional Info */}
        {(vehicle.year || vehicle.lastFuelDate) && (
          <div className="flex items-center gap-4 mt-3 pt-3 border-t text-sm text-muted-foreground">
            {vehicle.year && <span>Baujahr: {vehicle.year}</span>}
            {vehicle.lastFuelDate && (
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                Letzte Tankung: {formatDate(vehicle.lastFuelDate)}
              </span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default VehicleList;
