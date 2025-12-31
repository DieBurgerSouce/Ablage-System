/**
 * PropertiesPage - Immobilien-Übersicht
 *
 * Liste aller Immobilien mit Verwaltungsfunktionen
 */

import * as React from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { PropertyList } from '../components/properties/PropertyList';
import * as privatApi from '../api/privat-api';
import type { PrivatPropertyWithDetails } from '@/types/privat';
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

export function PropertiesPage() {
  const navigate = useNavigate();
  const { spaceId } = useParams({ strict: false }) as { spaceId?: string };

  const [properties, setProperties] = React.useState<PrivatPropertyWithDetails[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [deleteProperty, setDeleteProperty] = React.useState<PrivatPropertyWithDetails | null>(null);

  const pageSize = 12;

  // Load properties
  React.useEffect(() => {
    const loadProperties = async () => {
      if (!spaceId) {
        setError(new Error('Kein Bereich ausgewählt'));
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        const response = await privatApi.listProperties(spaceId, {
          page: page + 1,
          pageSize,
          search: searchQuery || undefined,
        });
        setProperties(response.items);
        setTotal(response.total);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Fehler beim Laden'));
      } finally {
        setIsLoading(false);
      }
    };
    loadProperties();
  }, [spaceId, page, searchQuery]);

  const handleSelectProperty = (property: PrivatPropertyWithDetails) => {
    navigate({
      to: '/privat/immobilien/$propertyId' as string,
      params: { propertyId: property.id },
    } as never);
  };

  const handleCreateProperty = () => {
    // TODO: Open create property dialog/form
    toast.info('Immobilien-Formular wird implementiert');
  };

  const handleEditProperty = (property: PrivatPropertyWithDetails) => {
    // TODO: Open edit property dialog/form
    toast.info('Immobilien-Formular wird implementiert');
  };

  const handleDeleteConfirm = async () => {
    if (!deleteProperty || !spaceId) return;

    try {
      await privatApi.deleteProperty(deleteProperty.id);
      setProperties((prev) => prev.filter((p) => p.id !== deleteProperty.id));
      setTotal((prev) => prev - 1);
      toast.success('Immobilie gelöscht');
    } catch (err) {
      toast.error('Fehler beim Löschen der Immobilie');
    } finally {
      setDeleteProperty(null);
    }
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    setPage(0);
  };

  return (
    <div className="p-8">
      <PropertyList
        properties={properties}
        total={total}
        page={page}
        pageSize={pageSize}
        isLoading={isLoading}
        error={error}
        onPageChange={setPage}
        onSelect={handleSelectProperty}
        onCreate={handleCreateProperty}
        onEdit={handleEditProperty}
        onDelete={setDeleteProperty}
        onSearch={handleSearch}
        searchQuery={searchQuery}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteProperty} onOpenChange={(open) => !open && setDeleteProperty(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Immobilie löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Immobilie "{deleteProperty?.name}" wirklich löschen?
              Alle zugehörigen Mieter und Dokumente werden ebenfalls gelöscht.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
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

export default PropertiesPage;
