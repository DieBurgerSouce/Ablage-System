/**
 * ContractsPage - Hauptseite für Vertragsmanagement
 *
 * Features:
 * - Dashboard mit KPIs
 * - Fristen-Warnungen
 * - Vertrags-Liste mit Filtern
 * - CRUD-Operationen
 * - Kalender-Export (iCal)
 * - Timeline-Ansicht
 */

import { useState, useCallback } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
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
import { RefreshCw, AlertTriangle, FileText, Calendar, BarChart3 } from 'lucide-react';
import type { Contract, ContractDetail, ContractListParams, ContractCreateRequest, ContractUpdateRequest } from '../types/contract-types';
import {
  useContracts,
  useContract,
  useContractSummary,
  useUpcomingDeadlines,
  useCreateContract,
  useUpdateContract,
  useDeleteContract,
  useRenewalDecision,
} from '../api/contracts-api';
import { ContractStatsCards } from '../components/ContractStatsCards';
import { ContractDeadlineAlerts } from '../components/ContractDeadlineAlerts';
import { ContractFilters } from '../components/ContractFilters';
import { ContractTable } from '../components/ContractTable';
import { ContractDetailSheet } from '../components/ContractDetailSheet';
import { ContractFormDialog } from '../components/ContractFormDialog';
import { ContractCalendarExport } from '../components/ContractCalendarExport';
import { ContractLifecycleDashboard } from '../components/ContractLifecycleDashboard';

const DEFAULT_PAGE_SIZE = 20;

export function ContractsPage() {
  void useNavigate();

  // Tab state
  const [activeTab, setActiveTab] = useState('contracts');

  // Filter state
  const [filters, setFilters] = useState<ContractListParams>({
    offset: 0,
    limit: DEFAULT_PAGE_SIZE,
    order_by: 'created_at',
    order_dir: 'desc',
  });

  // UI state
  const [selectedContractId, setSelectedContractId] = useState<string | null>(null);
  const [detailSheetOpen, setDetailSheetOpen] = useState(false);
  const [formDialogOpen, setFormDialogOpen] = useState(false);
  const [editContract, setEditContract] = useState<Contract | null>(null);
  const [deleteContract, setDeleteContract] = useState<Contract | null>(null);
  const [renewalConfirm, setRenewalConfirm] = useState<{
    contractId: string;
    optionId: string;
    decision: 'exercise' | 'decline';
  } | null>(null);

  // Queries
  const {
    data: contractsData,
    isLoading: isLoadingContracts,
    isError: isContractsError,
    refetch: refetchContracts,
    isFetching,
  } = useContracts(filters);

  const { data: summary, isLoading: isLoadingSummary } = useContractSummary();
  const { data: deadlines, isLoading: isLoadingDeadlines } = useUpcomingDeadlines(90);
  const {
    data: selectedContract,
    isLoading: isLoadingContract,
  } = useContract(selectedContractId || '', {
    enabled: !!selectedContractId,
  });

  // Mutations
  const createMutation = useCreateContract();
  const updateMutation = useUpdateContract();
  const deleteMutation = useDeleteContract();
  const renewalMutation = useRenewalDecision();

  // Handlers
  const handleFiltersChange = useCallback((newFilters: ContractListParams) => {
    setFilters(newFilters);
  }, []);

  const handleSort = useCallback((column: ContractListParams['order_by']) => {
    setFilters((prev) => ({
      ...prev,
      order_by: column,
      order_dir: prev.order_by === column && prev.order_dir === 'asc' ? 'desc' : 'asc',
      offset: 0,
    }));
  }, []);

  const handleViewContract = useCallback((contract: Contract) => {
    setSelectedContractId(contract.id);
    setDetailSheetOpen(true);
  }, []);

  const handleEditContract = useCallback((contract: Contract) => {
    setEditContract(contract);
    setFormDialogOpen(true);
  }, []);

  const handleCreateContract = useCallback(() => {
    setEditContract(null);
    setFormDialogOpen(true);
  }, []);

  const handleDeleteConfirm = async () => {
    if (!deleteContract) return;

    try {
      await deleteMutation.mutateAsync(deleteContract.id);
      toast.success('Vertrag gelöscht');
      setDeleteContract(null);
      setDetailSheetOpen(false);
    } catch (_error) {
      toast.error('Fehler beim Löschen des Vertrags');
    }
  };

  const handleFormSubmit = async (data: ContractCreateRequest | ContractUpdateRequest) => {
    try {
      if (editContract) {
        await updateMutation.mutateAsync({
          id: editContract.id,
          data: data as ContractUpdateRequest,
        });
        toast.success('Vertrag aktualisiert');
      } else {
        await createMutation.mutateAsync(data as ContractCreateRequest);
        toast.success('Vertrag erstellt');
      }
      setFormDialogOpen(false);
    } catch (error) {
      toast.error(editContract ? 'Fehler beim Aktualisieren' : 'Fehler beim Erstellen');
      throw error;
    }
  };

  const handleRenewalDecision = useCallback((optionId: string, decision: 'exercise' | 'decline') => {
    if (!selectedContractId) return;
    setRenewalConfirm({
      contractId: selectedContractId,
      optionId,
      decision,
    });
  }, [selectedContractId]);

  const handleRenewalConfirm = async () => {
    if (!renewalConfirm) return;

    try {
      await renewalMutation.mutateAsync({
        contractId: renewalConfirm.contractId,
        optionId: renewalConfirm.optionId,
        data: { decision: renewalConfirm.decision },
      });
      toast.success(
        renewalConfirm.decision === 'exercise'
          ? 'Verlängerung ausgeübt'
          : 'Verlängerung abgelehnt'
      );
      setRenewalConfirm(null);
    } catch (_error) {
      toast.error('Fehler bei der Verlängerungsentscheidung');
    }
  };

  const handleViewDeadlineContract = useCallback((contractId: string) => {
    setSelectedContractId(contractId);
    setDetailSheetOpen(true);
  }, []);

  const handleViewAllDeadlines = useCallback(() => {
    setFilters({
      ...filters,
      expiring_within_days: 90,
      offset: 0,
    });
  }, [filters]);

  // Pagination
  const currentPage = Math.floor((filters.offset || 0) / DEFAULT_PAGE_SIZE);
  const totalPages = Math.ceil((contractsData?.total || 0) / DEFAULT_PAGE_SIZE);

  const handlePageChange = (newPage: number) => {
    setFilters((prev) => ({
      ...prev,
      offset: newPage * DEFAULT_PAGE_SIZE,
    }));
  };

  // Error state
  if (isContractsError) {
    return (
      <Card className="m-8">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Fehler beim Laden
          </CardTitle>
          <CardDescription>
            Die Vertragsdaten konnten nicht geladen werden. Bitte versuchen Sie es erneut.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={() => refetchContracts()} variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" />
            Erneut versuchen
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="h-6 w-6" />
            Vertragsmanagement
          </h1>
          <p className="text-muted-foreground">
            Verwalten Sie Ihre B2B-Verträge, Fristen und Verlängerungen
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ContractCalendarExport
            trigger={
              <Button variant="outline" size="sm">
                <Calendar className="h-4 w-4 mr-2" />
                Kalender-Export
              </Button>
            }
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetchContracts()}
            disabled={isFetching}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
            Aktualisieren
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <ContractStatsCards summary={summary} isLoading={isLoadingSummary} />

      {/* Tabs: Verträge / Lifecycle */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="contracts" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Verträge
          </TabsTrigger>
          <TabsTrigger value="lifecycle" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Lifecycle
          </TabsTrigger>
        </TabsList>

        {/* Verträge Tab */}
        <TabsContent value="contracts" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-3">
            {/* Main Content */}
            <div className="lg:col-span-2 space-y-6">
              {/* Filters */}
              <Card>
                <CardContent className="pt-6">
                  <ContractFilters
                    filters={filters}
                    onFiltersChange={handleFiltersChange}
                    onCreateContract={handleCreateContract}
                  />
                </CardContent>
              </Card>

              {/* Table */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">
                    Verträge ({contractsData?.total || 0})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ContractTable
                    contracts={contractsData?.items || []}
                    isLoading={isLoadingContracts}
                    sortBy={filters.order_by}
                    sortDir={filters.order_dir}
                    onSort={handleSort}
                    onView={handleViewContract}
                    onEdit={handleEditContract}
                    onDelete={setDeleteContract}
                  />

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between mt-4">
                      <p className="text-sm text-muted-foreground">
                        Seite {currentPage + 1} von {totalPages}
                      </p>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handlePageChange(currentPage - 1)}
                          disabled={currentPage === 0}
                        >
                          Zurück
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handlePageChange(currentPage + 1)}
                          disabled={currentPage >= totalPages - 1}
                        >
                          Weiter
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Sidebar: Deadlines */}
            <div>
              <ContractDeadlineAlerts
                deadlines={deadlines?.items || []}
                isLoading={isLoadingDeadlines}
                onViewContract={handleViewDeadlineContract}
                onViewAll={handleViewAllDeadlines}
              />
            </div>
          </div>
        </TabsContent>

        {/* Lifecycle Tab */}
        <TabsContent value="lifecycle">
          <ContractLifecycleDashboard
            onViewContract={(contractId) => {
              setSelectedContractId(contractId);
              setDetailSheetOpen(true);
            }}
          />
        </TabsContent>
      </Tabs>

      {/* Detail Sheet */}
      <ContractDetailSheet
        contract={selectedContract as ContractDetail | null}
        open={detailSheetOpen}
        onOpenChange={setDetailSheetOpen}
        onEdit={() => {
          if (selectedContract) {
            handleEditContract(selectedContract as Contract);
          }
        }}
        onRenewalDecision={handleRenewalDecision}
        isLoading={isLoadingContract}
      />

      {/* Form Dialog */}
      <ContractFormDialog
        open={formDialogOpen}
        onOpenChange={setFormDialogOpen}
        contract={editContract}
        onSubmit={handleFormSubmit}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteContract} onOpenChange={(open) => !open && setDeleteContract(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Vertrag löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie den Vertrag "{deleteContract?.title}" ({deleteContract?.contract_number})
              wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.
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

      {/* Renewal Decision Confirmation */}
      <AlertDialog open={!!renewalConfirm} onOpenChange={(open) => !open && setRenewalConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {renewalConfirm?.decision === 'exercise'
                ? 'Verlängerung ausüben?'
                : 'Verlängerung ablehnen?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {renewalConfirm?.decision === 'exercise'
                ? 'Möchten Sie diese Verlängerungsoption ausüben? Der Vertrag wird entsprechend verlängert.'
                : 'Möchten Sie diese Verlängerungsoption ablehnen? Der Vertrag endet dann zum geplanten Termin.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRenewalConfirm}
              className={
                renewalConfirm?.decision === 'decline'
                  ? 'bg-orange-600 hover:bg-orange-700'
                  : undefined
              }
            >
              {renewalConfirm?.decision === 'exercise' ? 'Ausüben' : 'Ablehnen'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default ContractsPage;
