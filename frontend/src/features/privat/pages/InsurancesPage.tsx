/**
 * InsurancesPage - Versicherungen-Übersicht
 *
 * Liste aller Versicherungen mit Verwaltungsfunktionen
 */

import * as React from 'react';
import { useParams } from '@tanstack/react-router';
import { InsuranceList } from '../components/insurances/InsuranceList';
import * as privatApi from '../api/privat-api';
import type { PrivatInsuranceWithDeadlines, InsuranceType } from '@/types/privat';
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

export function InsurancesPage() {
  const { spaceId } = useParams({ strict: false }) as { spaceId?: string };

  const [insurances, setInsurances] = React.useState<PrivatInsuranceWithDeadlines[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [typeFilter, setTypeFilter] = React.useState<InsuranceType | 'all'>('all');
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [deleteInsurance, setDeleteInsurance] = React.useState<PrivatInsuranceWithDeadlines | null>(null);

  const pageSize = 12;

  // Load insurances
  React.useEffect(() => {
    const loadInsurances = async () => {
      if (!spaceId) {
        setError(new Error('Kein Bereich ausgewählt'));
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
  }, [spaceId, page, searchQuery, typeFilter]);

  const handleSelectInsurance = (insurance: PrivatInsuranceWithDeadlines) => {
    // TODO: Open detail view or navigate
    toast.info('Versicherungs-Detail wird implementiert');
  };

  const handleCreateInsurance = () => {
    // TODO: Open create insurance dialog/form
    toast.info('Versicherungs-Formular wird implementiert');
  };

  const handleEditInsurance = (insurance: PrivatInsuranceWithDeadlines) => {
    // TODO: Open edit insurance dialog/form
    toast.info('Versicherungs-Formular wird implementiert');
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
    </div>
  );
}

export default InsurancesPage;
