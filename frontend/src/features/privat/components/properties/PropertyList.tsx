/**
 * PropertyList - Immobilien-Übersicht
 *
 * Liste aller Immobilien mit Statistiken und Filterfunktion
 */

import * as React from 'react';
import { Link } from '@tanstack/react-router';
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
  Home,
  MapPin,
  Users,
  Euro,
  Edit,
  Trash2,
  Eye,
  Search,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import type { PrivatPropertyWithDetails } from '@/types/privat';
import { cn } from '@/lib/utils';

interface PropertyListProps {
  properties: PrivatPropertyWithDetails[];
  total: number;
  page: number;
  pageSize: number;
  isLoading?: boolean;
  error?: Error | null;
  onPageChange?: (page: number) => void;
  onSelect?: (property: PrivatPropertyWithDetails) => void;
  onEdit?: (property: PrivatPropertyWithDetails) => void;
  onDelete?: (property: PrivatPropertyWithDetails) => void;
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
    maximumFractionDigits: 0,
  }).format(amount);
};

const getPropertyTypeLabel = (type: string): string => {
  const types: Record<string, string> = {
    apartment: 'Wohnung',
    house: 'Haus',
    land: 'Grundstück',
    commercial: 'Gewerbe',
    garage: 'Garage',
    other: 'Sonstiges',
  };
  return types[type] || type;
};

export function PropertyList({
  properties,
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
}: PropertyListProps) {
  const totalPages = Math.ceil(total / pageSize);

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Immobilien</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Immobilien
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
          <div className="p-2 rounded-lg bg-green-100 dark:bg-green-950">
            <Home className="h-6 w-6 text-green-600 dark:text-green-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Immobilien</h1>
            <p className="text-muted-foreground">
              {total} {total === 1 ? 'Objekt' : 'Objekte'}
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
              Neues Objekt
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
      ) : properties.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Home className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">Keine Immobilien</h3>
            <p className="text-muted-foreground text-center mb-4">
              Erfassen Sie Ihre erste Immobilie, um Mieter und Einnahmen zu verwalten.
            </p>
            {onCreate && (
              <Button onClick={onCreate}>
                <Plus className="mr-2 h-4 w-4" />
                Immobilie hinzufügen
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {properties.map((property) => (
              <PropertyCard
                key={property.id}
                property={property}
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

interface PropertyCardProps {
  property: PrivatPropertyWithDetails;
  onSelect?: (property: PrivatPropertyWithDetails) => void;
  onEdit?: (property: PrivatPropertyWithDetails) => void;
  onDelete?: (property: PrivatPropertyWithDetails) => void;
}

function PropertyCard({ property, onSelect, onEdit, onDelete }: PropertyCardProps) {
  const address = [property.addressStreet, property.addressZip, property.addressCity]
    .filter(Boolean)
    .join(', ');

  return (
    <Card
      className={cn(
        'hover:shadow-md transition-shadow',
        onSelect && 'cursor-pointer'
      )}
      onClick={() => onSelect?.(property)}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <Badge variant="secondary" className="mb-2">
              {getPropertyTypeLabel(property.propertyType)}
            </Badge>
            <CardTitle className="text-lg">{property.name}</CardTitle>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onSelect?.(property)}>
                <Eye className="mr-2 h-4 w-4" />
                Details
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onEdit?.(property)}>
                <Edit className="mr-2 h-4 w-4" />
                Bearbeiten
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => onDelete?.(property)}
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
        {/* Address */}
        {address && (
          <div className="flex items-start gap-2 text-sm text-muted-foreground mb-4">
            <MapPin className="h-4 w-4 mt-0.5 flex-shrink-0" />
            <span>{address}</span>
          </div>
        )}

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-3">
          {/* Tenants */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <Users className="h-4 w-4 text-blue-500" />
            <div>
              <p className="text-xs text-muted-foreground">Mieter</p>
              <p className="font-medium">{property.tenants?.length ?? 0}</p>
            </div>
          </div>

          {/* Occupancy */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <Home className="h-4 w-4 text-green-500" />
            <div>
              <p className="text-xs text-muted-foreground">Auslastung</p>
              <p className="font-medium">{property.occupancyRate?.toFixed(0) ?? 0}%</p>
            </div>
          </div>

          {/* Rental Income */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <Euro className="h-4 w-4 text-amber-500" />
            <div>
              <p className="text-xs text-muted-foreground">Monatl. Einnahmen</p>
              <p className="font-medium">{formatCurrency(property.totalRentalIncome)}</p>
            </div>
          </div>

          {/* Current Value */}
          <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
            <Home className="h-4 w-4 text-purple-500" />
            <div>
              <p className="text-xs text-muted-foreground">Wert</p>
              <p className="font-medium">{formatCurrency(property.currentValue)}</p>
            </div>
          </div>
        </div>

        {/* Size Info */}
        {(property.sizeSqm || property.rooms) && (
          <div className="flex items-center gap-4 mt-3 pt-3 border-t text-sm text-muted-foreground">
            {property.sizeSqm && <span>{property.sizeSqm} m2</span>}
            {property.rooms && (
              <span>{property.rooms} {property.rooms === 1 ? 'Zimmer' : 'Zimmer'}</span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default PropertyList;
