/**
 * Contract Dashboard Route
 *
 * Route: /contracts/dashboard
 *
 * Features:
 * - Vertragsueberblick mit erweiterten Statistiken
 * - Fristen-Kalenderansicht
 * - Schnellaktionen fuer kritische Vertraege
 */

import { useState, useCallback } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  FileText,
  Calendar,
  AlertTriangle,
  RefreshCw,
  ListFilter,
  LayoutGrid,
} from 'lucide-react';
import {
  useContracts,
  useContractSummary,
  useUpcomingDeadlines,
  useUpdateContract,
} from '@/features/contracts/api/contracts-api';
import { ContractStatsCards } from '@/features/contracts/components/ContractStatsCards';
import { ContractDeadlineAlerts } from '@/features/contracts/components/ContractDeadlineAlerts';
import { ContractDeadlineCalendar } from '@/features/contracts/components/ContractDeadlineCalendar';
import { ContractQuickActions } from '@/features/contracts/components/ContractQuickActions';
import { ContractTable } from '@/features/contracts/components/ContractTable';
import { ContractDetailSheet } from '@/features/contracts/components/ContractDetailSheet';
import type { Contract, ContractDetail, DeadlineAlert, ContractListParams } from '@/features/contracts/types/contract-types';

function ContractDashboardPage() {
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedContractId, setSelectedContractId] = useState<string | null>(null);
  const [detailSheetOpen, setDetailSheetOpen] = useState(false);

  // Queries
  const { data: summary, isLoading: isLoadingSummary, refetch: refetchSummary } = useContractSummary();
  const { data: deadlines, isLoading: isLoadingDeadlines } = useUpcomingDeadlines(90);
  const { data: criticalContracts, isLoading: isLoadingCritical } = useContracts({
    expiring_within_days: 30,
    limit: 10,
    order_by: 'notice_deadline',
    order_dir: 'asc',
  });
  const { data: selectedContract, isLoading: isLoadingContract } = useContracts(
    { search: selectedContractId || '' },
    { enabled: !!selectedContractId }
  );

  // Mutations
  const updateMutation = useUpdateContract();

  const isLoading = isLoadingSummary || isLoadingDeadlines || isLoadingCritical;

  // Handlers
  const handleViewContract = useCallback((contractId: string) => {
    setSelectedContractId(contractId);
    setDetailSheetOpen(true);
  }, []);

  const handleDeadlineSelect = useCallback((deadline: DeadlineAlert) => {
    handleViewContract(deadline.contract_id);
  }, [handleViewContract]);

  const handleRenewContract = useCallback(async (contract: Contract) => {
    try {
      await updateMutation.mutateAsync({
        id: contract.id,
        data: {
          status: 'renewed',
        },
      });
      toast.success('Vertrag als verlaengert markiert');
      refetchSummary();
    } catch (error) {
      toast.error('Fehler beim Verlaengern des Vertrags');
    }
  }, [updateMutation, refetchSummary]);

  const handleTerminateContract = useCallback(async (contract: Contract, reason: string) => {
    try {
      await updateMutation.mutateAsync({
        id: contract.id,
        data: {
          status: 'terminated',
          termination_reason: reason,
          terminated_date: new Date().toISOString(),
        },
      });
      toast.success('Vertrag gekuendigt');
      refetchSummary();
    } catch (error) {
      toast.error('Fehler beim Kuendigen des Vertrags');
    }
  }, [updateMutation, refetchSummary]);

  const handleArchiveContract = useCallback(async (contract: Contract) => {
    try {
      await updateMutation.mutateAsync({
        id: contract.id,
        data: {
          metadata: {
            ...contract.metadata,
            archived: true,
            archived_at: new Date().toISOString(),
          },
        },
      });
      toast.success('Vertrag archiviert');
      refetchSummary();
    } catch (error) {
      toast.error('Fehler beim Archivieren des Vertrags');
    }
  }, [updateMutation, refetchSummary]);

  if (isLoading) {
    return (
      <div className="p-8 space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-[400px]" />
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="h-6 w-6" />
            Vertrags-Dashboard
          </h1>
          <p className="text-muted-foreground">
            Ueberblick ueber alle Vertraege, Fristen und anstehende Aktionen
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetchSummary()}
          disabled={isLoadingSummary}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoadingSummary ? 'animate-spin' : ''}`} />
          Aktualisieren
        </Button>
      </div>

      {/* Stats Cards */}
      <ContractStatsCards summary={summary} isLoading={isLoadingSummary} />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <LayoutGrid className="h-4 w-4" />
            Ueberblick
          </TabsTrigger>
          <TabsTrigger value="calendar" className="flex items-center gap-2">
            <Calendar className="h-4 w-4" />
            Kalender
          </TabsTrigger>
          <TabsTrigger value="critical" className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Kritische Fristen
            {(summary?.critical_deadlines ?? 0) > 0 && (
              <span className="ml-1 bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5">
                {summary?.critical_deadlines}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-3">
            {/* Deadline Alerts */}
            <div className="lg:col-span-2">
              <ContractDeadlineAlerts
                deadlines={deadlines?.items || []}
                isLoading={isLoadingDeadlines}
                onViewContract={handleViewContract}
                onViewAll={() => setActiveTab('critical')}
              />
            </div>

            {/* Quick Stats */}
            <div className="space-y-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Vertragsvolumen</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {(summary?.total_value ?? 0).toLocaleString('de-DE', {
                      style: 'currency',
                      currency: 'EUR',
                    })}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Monatlich: {(summary?.monthly_commitment ?? 0).toLocaleString('de-DE', {
                      style: 'currency',
                      currency: 'EUR',
                    })}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Status-Verteilung</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Aktiv</span>
                      <span className="font-medium">{summary?.active_contracts ?? 0}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-orange-600">Bald ablaufend</span>
                      <span className="font-medium text-orange-600">{summary?.expiring_soon ?? 0}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-red-600">Kritisch</span>
                      <span className="font-medium text-red-600">{summary?.critical_deadlines ?? 0}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        {/* Calendar Tab */}
        <TabsContent value="calendar">
          <ContractDeadlineCalendar
            deadlines={deadlines?.items || []}
            isLoading={isLoadingDeadlines}
            onSelectDeadline={handleDeadlineSelect}
          />
        </TabsContent>

        {/* Critical Tab */}
        <TabsContent value="critical" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-red-500" />
                Kritische und bald ablaufende Vertraege
              </CardTitle>
              <CardDescription>
                Vertraege mit Fristen in den naechsten 30 Tagen
              </CardDescription>
            </CardHeader>
            <CardContent>
              {criticalContracts?.items && criticalContracts.items.length > 0 ? (
                <div className="space-y-4">
                  {criticalContracts.items.map((contract) => (
                    <div
                      key={contract.id}
                      className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <h4 className="font-medium truncate">{contract.title}</h4>
                          <span className="text-sm text-muted-foreground">
                            ({contract.contract_number})
                          </span>
                        </div>
                        <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
                          {contract.party_a_name && (
                            <span>{contract.party_a_name}</span>
                          )}
                          {contract.days_until_end !== undefined && (
                            <span className={contract.days_until_end <= 14 ? 'text-red-600 font-medium' : ''}>
                              Endet in {contract.days_until_end} Tagen
                            </span>
                          )}
                        </div>
                      </div>
                      <ContractQuickActions
                        contract={contract}
                        onView={() => handleViewContract(contract.id)}
                        onRenew={handleRenewContract}
                        onTerminate={handleTerminateContract}
                        onArchive={handleArchiveContract}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <AlertTriangle className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>Keine kritischen Fristen in den naechsten 30 Tagen</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Detail Sheet */}
      <ContractDetailSheet
        contract={selectedContract?.items?.[0] as ContractDetail | null}
        open={detailSheetOpen}
        onOpenChange={setDetailSheetOpen}
        onEdit={() => {
          // Navigate to edit page or open edit dialog
        }}
        onRenewalDecision={() => {
          // Handle renewal decision
        }}
        isLoading={isLoadingContract}
      />
    </div>
  );
}

export const Route = createFileRoute('/contracts/dashboard')({
  component: ContractDashboardPage,
});
