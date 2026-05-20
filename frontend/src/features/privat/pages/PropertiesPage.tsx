/**
 * PropertiesPage - Immobilien-Übersicht
 *
 * Liste aller Immobilien mit Verwaltungsfunktionen
 */

import * as React from 'react';
import { useNavigate, useParams, useSearch } from '@tanstack/react-router';
import { PropertyList } from '../components/properties/PropertyList';
import { PropertyCreateDialog } from '../components/properties/PropertyCreateDialog';
import { PropertyEditDialog } from '../components/properties/PropertyEditDialog';
import * as privatApi from '../api/privat-api';
import { useDefaultSpace } from '../hooks/use-privat-queries';
import type { PrivatPropertyWithDetails, PrivatPropertyCreate, PrivatPropertyUpdate } from '@/types/privat';
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

interface PropertiesPageProps {
  spaceId?: string;
}

export function PropertiesPage({ spaceId: propSpaceId }: PropertiesPageProps = {}) {
  const navigate = useNavigate();
  const params = useParams({ strict: false }) as { spaceId?: string };
  const search = useSearch({ strict: false }) as { space?: string };
  const { defaultSpaceId, isLoading: isLoadingSpaces, hasSpaces } = useDefaultSpace();

  // Priorität: 1. Props, 2. URL-Params, 3. Query-Param (?space=), 4. Default-Space
  const spaceId = propSpaceId || params.spaceId || search.space || defaultSpaceId;

  const [properties, setProperties] = React.useState<PrivatPropertyWithDetails[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [deleteProperty, setDeleteProperty] = React.useState<PrivatPropertyWithDetails | null>(null);

  // Dialog state
  const [showCreateDialog, setShowCreateDialog] = React.useState(false);
  const [editProperty, setEditProperty] = React.useState<PrivatPropertyWithDetails | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const pageSize = 12;

  // Load properties
  React.useEffect(() => {
    const loadProperties = async () => {
      // Warte auf Spaces wenn noch keine spaceId vorhanden
      if (isLoadingSpaces && !spaceId) {
        return;
      }

      if (!spaceId) {
        if (!hasSpaces) {
          setError(new Error('Noch keine Bereiche vorhanden. Erstellen Sie zuerst einen persönlichen Bereich.'));
        } else {
          setError(new Error('Kein Bereich ausgewählt'));
        }
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
  }, [spaceId, page, searchQuery, isLoadingSpaces, hasSpaces]);

  const handleSelectProperty = (property: PrivatPropertyWithDetails) => {
    void navigate({
      to: `/privat/immobilien/${property.id}`,
    });
  };

  const handleCreateProperty = () => {
    setShowCreateDialog(true);
  };

  const handleEditProperty = (property: PrivatPropertyWithDetails) => {
    setEditProperty(property);
  };

  const handleCreateSubmit = async (data: PrivatPropertyCreate) => {
    if (!spaceId) return;
    setIsSubmitting(true);
    try {
      const newProperty = await privatApi.createProperty(spaceId, data);
      setProperties((prev) => [newProperty, ...prev]);
      setTotal((prev) => prev + 1);
      toast.success('Immobilie erstellt');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEditSubmit = async (propertyId: string, data: PrivatPropertyUpdate) => {
    setIsSubmitting(true);
    try {
      const updated = await privatApi.updateProperty(propertyId, data);
      setProperties((prev) => prev.map((p) => (p.id === propertyId ? updated : p)));
      toast.success('Immobilie aktualisiert');
    } finally {
      setIsSubmitting(false);
    }
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

      {/* Create Dialog */}
      <PropertyCreateDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        onSubmit={handleCreateSubmit}
        isLoading={isSubmitting}
      />

      {/* Edit Dialog */}
      <PropertyEditDialog
        open={!!editProperty}
        onOpenChange={(open) => !open && setEditProperty(null)}
        property={editProperty}
        onSubmit={handleEditSubmit}
        isLoading={isSubmitting}
      />
    </div>
  );
}

export default PropertiesPage;
