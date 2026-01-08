/**
 * PropertyDetailPage - Immobilien-Detailansicht
 *
 * Zeigt alle Details einer Immobilie inkl. Mieter und Mieteinnahmen
 */

import * as React from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { ArrowLeft, Edit, Trash2, MapPin, Home, Users, Euro, Calendar, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
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
import { toast } from 'sonner';
import * as privatApi from '../api/privat-api';
import type { PrivatPropertyWithDetails, PrivatPropertyUpdate } from '@/types/privat';
import { PropertyEditDialog } from '../components/properties/PropertyEditDialog';
import { DocumentUploadSection } from '../components/shared/DocumentUploadSection';

const PROPERTY_TYPE_LABELS: Record<string, string> = {
  apartment: 'Wohnung',
  house: 'Haus',
  commercial: 'Gewerbe',
  land: 'Grundstück',
  garage: 'Garage/Stellplatz',
  other: 'Sonstiges',
};

export function PropertyDetailPage() {
  const navigate = useNavigate();
  const { propertyId } = useParams({ strict: false }) as { propertyId: string };

  const [property, setProperty] = React.useState<PrivatPropertyWithDetails | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = React.useState(false);
  const [showEditDialog, setShowEditDialog] = React.useState(false);
  const [isUpdating, setIsUpdating] = React.useState(false);

  // Load property details
  React.useEffect(() => {
    const loadProperty = async () => {
      if (!propertyId) {
        setError(new Error('Keine Immobilien-ID angegeben'));
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        const data = await privatApi.getProperty(propertyId);
        setProperty(data);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Fehler beim Laden der Immobilie'));
      } finally {
        setIsLoading(false);
      }
    };
    loadProperty();
  }, [propertyId]);

  const handleEdit = async (propId: string, data: PrivatPropertyUpdate) => {
    setIsUpdating(true);
    try {
      const updated = await privatApi.updateProperty(propId, data);
      setProperty(updated);
      toast.success('Immobilie aktualisiert');
    } catch (err) {
      toast.error('Fehler beim Aktualisieren');
      throw err;
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = async () => {
    if (!property) return;

    try {
      await privatApi.deleteProperty(property.id);
      toast.success('Immobilie gelöscht');
      navigate({ to: '/privat/immobilien' });
    } catch (err) {
      toast.error('Fehler beim Löschen der Immobilie');
    } finally {
      setShowDeleteDialog(false);
    }
  };

  const handleBack = () => {
    navigate({ to: '/privat/immobilien' });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !property) {
    return (
      <div className="p-8">
        <div className="text-center py-12">
          <p className="text-destructive mb-4">{error?.message || 'Immobilie nicht gefunden'}</p>
          <Button variant="outline" onClick={handleBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Zurück zur Übersicht
          </Button>
        </div>
      </div>
    );
  }

  const fullAddress = [
    property.addressStreet,
    [property.addressZip, property.addressCity].filter(Boolean).join(' '),
    property.addressCountry,
  ].filter(Boolean).join(', ');

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold">{property.name}</h1>
            <p className="text-muted-foreground">
              {PROPERTY_TYPE_LABELS[property.propertyType] || property.propertyType}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setShowEditDialog(true)}>
            <Edit className="mr-2 h-4 w-4" />
            Bearbeiten
          </Button>
          <Button variant="destructive" onClick={() => setShowDeleteDialog(true)}>
            <Trash2 className="mr-2 h-4 w-4" />
            Löschen
          </Button>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Basic Info Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Home className="h-5 w-5" />
              Details
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {fullAddress && (
              <div className="flex items-start gap-2">
                <MapPin className="h-4 w-4 mt-0.5 text-muted-foreground" />
                <span className="text-sm">{fullAddress}</span>
              </div>
            )}
            {property.sizeSqm && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Fläche</span>
                <span>{property.sizeSqm.toLocaleString('de-DE')} m²</span>
              </div>
            )}
            {property.rooms && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Zimmer</span>
                <span>{property.rooms}</span>
              </div>
            )}
            {property.purchaseDate && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Kaufdatum</span>
                <span>{new Date(property.purchaseDate).toLocaleDateString('de-DE')}</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Financial Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Euro className="h-5 w-5" />
              Finanzen
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {property.purchasePrice !== undefined && property.purchasePrice !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Kaufpreis</span>
                <span>{property.purchasePrice.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
              </div>
            )}
            {property.currentValue !== undefined && property.currentValue !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Aktueller Wert</span>
                <span className="font-medium">{property.currentValue.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
              </div>
            )}
            {property.totalRentalIncome > 0 && (
              <>
                <Separator />
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Mieteinnahmen (gesamt)</span>
                  <span className="text-green-600">{property.totalRentalIncome.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
                </div>
              </>
            )}
            {property.averageRent > 0 && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Durchschnittsmiete</span>
                <span>{property.averageRent.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}/Monat</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Occupancy Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Belegung
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Auslastung</span>
              <Badge variant={property.occupancyRate >= 80 ? 'default' : property.occupancyRate >= 50 ? 'secondary' : 'destructive'}>
                {property.occupancyRate.toFixed(0)}%
              </Badge>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Aktive Mieter</span>
              <span>{property.tenants.filter(t => t.isActive).length}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tenants Section */}
      {property.tenants.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Mieter</CardTitle>
            <CardDescription>Aktuelle und ehemalige Mieter dieser Immobilie</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {property.tenants.map((tenant) => (
                <div key={tenant.id} className="flex items-center justify-between p-3 rounded-lg border">
                  <div>
                    <p className="font-medium">
                      {tenant.firstName} {tenant.lastName}
                      {!tenant.isActive && <Badge variant="secondary" className="ml-2">Ausgezogen</Badge>}
                    </p>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      {tenant.email && <span>{tenant.email}</span>}
                      {tenant.moveInDate && (
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          Einzug: {new Date(tenant.moveInDate).toLocaleDateString('de-DE')}
                        </span>
                      )}
                    </div>
                  </div>
                  {tenant.monthlyRent && (
                    <div className="text-right">
                      <p className="font-medium">{tenant.monthlyRent.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</p>
                      <p className="text-sm text-muted-foreground">pro Monat</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Notes Section */}
      {property.notes && (
        <Card>
          <CardHeader>
            <CardTitle>Notizen</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap">{property.notes}</p>
          </CardContent>
        </Card>
      )}

      {/* Edit Dialog */}
      <PropertyEditDialog
        open={showEditDialog}
        onOpenChange={setShowEditDialog}
        property={property}
        onSubmit={handleEdit}
        isLoading={isUpdating}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Immobilie löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Immobilie "{property.name}" wirklich löschen?
              Alle zugehörigen Mieter und Dokumente werden ebenfalls gelöscht.
              Diese Aktion kann nicht rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default PropertyDetailPage;
