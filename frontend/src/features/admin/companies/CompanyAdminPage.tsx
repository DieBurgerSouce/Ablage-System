/**
 * CompanyAdminPage - Firmenverwaltung für Administratoren
 *
 * Features:
 * - Firmen-Übersicht mit Tabelle
 * - CRUD-Operationen
 * - Benutzer-Verwaltung pro Firma
 * - Multi-Mandanten-Management für 20+ Firmen
 */

import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Building2, Plus, RefreshCw } from 'lucide-react';
import {
  useCompaniesAdmin,
  useCreateCompany,
  useUpdateCompany,
  useDeleteCompany,
} from './api/companies-admin-api';
import { CompanyTable } from './components/CompanyTable';
import { CompanyFormDialog } from './components/CompanyFormDialog';
import { CompanyUsersDialog } from './components/CompanyUsersDialog';
import { useCompany } from '@/context/CompanyContext';
import type {
  Company,
  CompanyCreate,
  CompanyUpdate,
} from '@/types/models/company';
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

export function CompanyAdminPage() {
  const { toast } = useToast();
  const { currentCompany } = useCompany();

  // Filter state
  const [includeInactive, setIncludeInactive] = useState(true);

  // Dialog states
  const [formDialogOpen, setFormDialogOpen] = useState(false);
  const [usersDialogOpen, setUsersDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);

  // Queries
  const {
    data: companiesData,
    isLoading,
    refetch,
  } = useCompaniesAdmin({ include_inactive: includeInactive });

  // Mutations
  const createCompany = useCreateCompany();
  const updateCompany = useUpdateCompany();
  const deleteCompanyMut = useDeleteCompany();

  // Handlers
  const handleEdit = useCallback((company: Company) => {
    setSelectedCompany(company);
    setFormDialogOpen(true);
  }, []);

  const handleDelete = useCallback((company: Company) => {
    setSelectedCompany(company);
    setDeleteDialogOpen(true);
  }, []);

  const handleManageUsers = useCallback((company: Company) => {
    setSelectedCompany(company);
    setUsersDialogOpen(true);
  }, []);

  const handleSetDefault = useCallback(
    async (company: Company) => {
      try {
        await updateCompany.mutateAsync({
          id: company.id,
          data: { is_default: !company.is_default },
        });
        toast({
          title: company.is_default ? 'Standard entfernt' : 'Als Standard gesetzt',
          description: company.is_default
            ? 'Die Firma ist nicht mehr Standard.'
            : 'Diese Firma ist jetzt die Standard-Firma.',
        });
      } catch (error) {
        toast({
          title: 'Fehler',
          description: 'Der Status konnte nicht geändert werden.',
          variant: 'destructive',
        });
      }
    },
    [updateCompany, toast]
  );

  const handleToggleActive = useCallback(
    async (company: Company) => {
      try {
        await updateCompany.mutateAsync({
          id: company.id,
          data: { is_active: !company.is_active },
        });
        toast({
          title: company.is_active ? 'Firma deaktiviert' : 'Firma aktiviert',
          description: company.is_active
            ? 'Die Firma wurde deaktiviert.'
            : 'Die Firma wurde aktiviert.',
        });
      } catch (error) {
        toast({
          title: 'Fehler',
          description: 'Der Status konnte nicht geändert werden.',
          variant: 'destructive',
        });
      }
    },
    [updateCompany, toast]
  );

  const handleCreateOrUpdate = useCallback(
    async (data: CompanyCreate | CompanyUpdate) => {
      try {
        if (selectedCompany) {
          await updateCompany.mutateAsync({ id: selectedCompany.id, data });
          toast({
            title: 'Firma aktualisiert',
            description: 'Die Änderungen wurden gespeichert.',
          });
        } else {
          await createCompany.mutateAsync(data as CompanyCreate);
          toast({
            title: 'Firma erstellt',
            description: 'Die neue Firma wurde erstellt.',
          });
        }
        setFormDialogOpen(false);
        setSelectedCompany(null);
      } catch (error) {
        toast({
          title: 'Fehler',
          description: 'Die Firma konnte nicht gespeichert werden.',
          variant: 'destructive',
        });
      }
    },
    [selectedCompany, createCompany, updateCompany, toast]
  );

  const handleConfirmDelete = useCallback(async () => {
    if (!selectedCompany) return;

    try {
      await deleteCompanyMut.mutateAsync(selectedCompany.id);
      toast({
        title: 'Firma gelöscht',
        description: 'Die Firma wurde erfolgreich gelöscht.',
      });
      setDeleteDialogOpen(false);
      setSelectedCompany(null);
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Die Firma konnte nicht gelöscht werden.',
        variant: 'destructive',
      });
    }
  }, [selectedCompany, deleteCompanyMut, toast]);

  const companies = companiesData?.items ?? [];

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Building2 className="h-8 w-8" />
            Firmenverwaltung
          </h1>
          <p className="text-muted-foreground mt-1">
            Multi-Mandanten-Verwaltung für Ihr Ablage-System
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Switch
              id="include-inactive"
              checked={includeInactive}
              onCheckedChange={setIncludeInactive}
            />
            <Label htmlFor="include-inactive" className="text-sm">
              Inaktive anzeigen
            </Label>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Aktualisieren
          </Button>
          <Button
            onClick={() => {
              setSelectedCompany(null);
              setFormDialogOpen(true);
            }}
          >
            <Plus className="h-4 w-4 mr-2" />
            Neue Firma
          </Button>
        </div>
      </div>

      {/* Summary */}
      <div className="flex items-center gap-4 text-sm text-muted-foreground">
        <span>
          <strong>{companies.length}</strong> Firmen insgesamt
        </span>
        <span>|</span>
        <span>
          <strong>{companies.filter((c) => c.is_active).length}</strong> aktiv
        </span>
        {currentCompany && (
          <>
            <span>|</span>
            <span>
              Aktuelle Firma: <strong>{currentCompany.name}</strong>
            </span>
          </>
        )}
      </div>

      {/* Table */}
      <CompanyTable
        companies={companies}
        isLoading={isLoading}
        currentCompanyId={currentCompany?.id}
        onEdit={handleEdit}
        onDelete={handleDelete}
        onManageUsers={handleManageUsers}
        onSetDefault={handleSetDefault}
        onToggleActive={handleToggleActive}
      />

      {/* Dialogs */}
      <CompanyFormDialog
        open={formDialogOpen}
        onOpenChange={(open) => {
          setFormDialogOpen(open);
          if (!open) setSelectedCompany(null);
        }}
        company={selectedCompany}
        onSubmit={handleCreateOrUpdate}
        isSubmitting={createCompany.isPending || updateCompany.isPending}
      />

      <CompanyUsersDialog
        open={usersDialogOpen}
        onOpenChange={(open) => {
          setUsersDialogOpen(open);
          if (!open) setSelectedCompany(null);
        }}
        company={selectedCompany}
      />

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Firma löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Firma &quot;{selectedCompany?.name}&quot; wirklich löschen?
              Diese Aktion kann nicht rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
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
