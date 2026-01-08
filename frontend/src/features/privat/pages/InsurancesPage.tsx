/**
 * InsurancesPage - Versicherungen-Übersicht
 *
 * Liste aller Versicherungen mit Verwaltungsfunktionen
 */

import * as React from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { InsuranceList } from '../components/insurances/InsuranceList';
import { InsuranceCreateDialog } from '../components/insurances/InsuranceCreateDialog';
import { InsuranceEditDialog } from '../components/insurances/InsuranceEditDialog';
import * as privatApi from '../api/privat-api';
import { useDefaultSpace } from '../hooks/use-privat-queries';
import type { PrivatInsuranceWithDeadlines, InsuranceType, PrivatInsuranceCreate, PrivatInsuranceUpdate } from '@/types/privat';
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

interface InsurancesPageProps {
  spaceId?: string;
}

export function InsurancesPage({ spaceId: propSpaceId }: InsurancesPageProps = {}) {
  const navigate = useNavigate();
  const params = useParams({ strict: false }) as { spaceId?: string };
  const { defaultSpaceId, isLoading: isLoadingSpaces, hasSpaces } = useDefaultSpace();

  // Priorität: 1. Props, 2. URL-Params, 3. Default-Space (persönlicher Bereich)
  const spaceId = propSpaceId || params.spaceId || defaultSpaceId;

  const [insurances, setInsurances] = React.useState<PrivatInsuranceWithDeadlines[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [typeFilter, setTypeFilter] = React.useState<InsuranceType | 'all'>('all');
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [deleteInsurance, setDeleteInsurance] = React.useState<PrivatInsuranceWithDeadlines | null>(null);

  // Dialog state
  const [showCreateDialog, setShowCreateDialog] = React.useState(false);
  const [editInsurance, setEditInsurance] = React.useState<PrivatInsuranceWithDeadlines | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const pageSize = 12;

  // Load insurances
  React.useEffect(() => {
    const loadInsurances = async () => {
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
        const response = await privatApi.listInsurances(spaceId, {
          page: page + 1,
          pageSize,
          search: searchQuery || undefined,
          insuranceType: typeFilter !== 'all' ? typeFilter : undefined,
        });
        setInsurances(response.items);
        setTotal(response.total);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Fehler beim Laden'));
      } finally {
        setIsLoading(false);
      }
    };
    loadInsurances();
  }, [spaceId, page, searchQuery, typeFilter, isLoadingSpaces, hasSpaces]);

  const handleSelectInsurance = (insurance: PrivatInsuranceWithDeadlines) => {
    void navigate({
      to: `/privat/versicherungen/${insurance.id}`,
    });
  };

  const handleCreateInsurance = () => {
    setShowCreateDialog(true);
  };

  const handleEditInsurance = (insurance: PrivatInsuranceWithDeadlines) => {
    setEditInsurance(insurance);
  };

  const handleCreateSubmit = async (data: PrivatInsuranceCreate) => {
    if (!spaceId) return;
    setIsSubmitting(true);
    try {
      const newInsurance = await privatApi.createInsurance(spaceId, data);
      setInsurances((prev) => [newInsurance, ...prev]);
      setTotal((prev) => prev + 1);
      toast.success('Versicherung erstellt');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEditSubmit = async (insuranceId: string, data: PrivatInsuranceUpdate) => {
    setIsSubmitting(true);
    try {
      const updated = await privatApi.updateInsurance(insuranceId, data);
      setInsurances((prev) => prev.map((i) => (i.id === insuranceId ? updated : i)));
      toast.success('Versicherung aktualisiert');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteInsurance || !spaceId) return;

    try {
      await privatApi.deleteInsurance(deleteInsurance.id);
      setInsurances((prev) => prev.filter((i) => i.id !== deleteInsurance.id));
      setTotal((prev) => prev - 1);
      toast.success('Versicherung gelöscht');
    } catch (err) {
      toast.error('Fehler beim Löschen der Versicherung');
    } finally {
      setDeleteInsurance(null);
    }
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    setPage(0);
  };

  const handleTypeFilter = (type: InsuranceType | 'all') => {
    setTypeFilter(type);
    setPage(0);
  };

  return (
    <div className="p-8">
      <InsuranceList
        insurances={insurances}
        total={total}
        page={page}
        pageSize={pageSize}
        isLoading={isLoading}
        error={error}
        onPageChange={setPage}
        onSelect={handleSelectInsurance}
        onCreate={handleCreateInsurance}
        onEdit={handleEditInsurance}
        onDelete={setDeleteInsurance}
        onSearch={handleSearch}
        onTypeFilter={handleTypeFilter}
        selectedType={typeFilter}
        searchQuery={searchQuery}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteInsurance} onOpenChange={(open) => !open && setDeleteInsurance(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Versicherung löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Versicherung "{deleteInsurance?.name}" wirklich löschen?
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
      <InsuranceCreateDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        onSubmit={handleCreateSubmit}
        isLoading={isSubmitting}
      />

      {/* Edit Dialog */}
      <InsuranceEditDialog
        open={!!editInsurance}
        onOpenChange={(open) => !open && setEditInsurance(null)}
        insurance={editInsurance}
        onSubmit={handleEditSubmit}
        isLoading={isSubmitting}
      />
    </div>
  );
}

export default InsurancesPage;
