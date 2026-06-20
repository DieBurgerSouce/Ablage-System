/**
 * DelegationPortal Component
 *
 * Main page for managing delegations (Vertretungsregelungen)
 */

import { useState } from 'react';
import {
  Users,
  ArrowUpRight,
  ArrowDownLeft,
  RefreshCw,
  Info,
  AlertCircle,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { DelegationCard } from './components/DelegationCard';
import { CreateDelegationDialog } from './components/CreateDelegationDialog';
import {
  DeclineDelegationDialog,
  RevokeDelegationDialog,
  ExtendDelegationDialog,
} from './components/DelegationActionDialogs';
import {
  useDelegations,
  useCreateDelegation,
  useAcceptDelegation,
  useDeclineDelegation,
  useRevokeDelegation,
  useExtendDelegation,
} from './hooks';
import { DelegationStatus } from './types';
import type { Delegation, DelegationCreateRequest } from './types';

// Mock current user ID - should come from auth context
const CURRENT_USER_ID = 'current-user-id';

export function DelegationPortal() {
  // Queries for given and received delegations
  const {
    data: givenData,
    isLoading: isLoadingGiven,
    refetch: refetchGiven,
  } = useDelegations({ direction: 'given' });
  const {
    data: receivedData,
    isLoading: isLoadingReceived,
    refetch: refetchReceived,
  } = useDelegations({ direction: 'received' });

  // Mutations
  const createMutation = useCreateDelegation();
  const acceptMutation = useAcceptDelegation();
  const declineMutation = useDeclineDelegation();
  const revokeMutation = useRevokeDelegation();
  const extendMutation = useExtendDelegation();

  // Dialog state
  const [declineTarget, setDeclineTarget] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);
  const [extendTarget, setExtendTarget] = useState<Delegation | null>(null);

  const isLoading = isLoadingGiven || isLoadingReceived;
  const isAnyMutating =
    createMutation.isPending ||
    acceptMutation.isPending ||
    declineMutation.isPending ||
    revokeMutation.isPending ||
    extendMutation.isPending;

  const handleRefresh = () => {
    refetchGiven();
    refetchReceived();
  };

  const handleCreate = (request: DelegationCreateRequest) => {
    createMutation.mutate(request);
  };

  const handleAccept = (id: string) => {
    acceptMutation.mutate(id);
  };

  const handleDecline = (reason?: string) => {
    if (declineTarget) {
      declineMutation.mutate({ delegationId: declineTarget, reason });
      setDeclineTarget(null);
    }
  };

  const handleRevoke = (reason?: string) => {
    if (revokeTarget) {
      revokeMutation.mutate({ delegationId: revokeTarget, reason });
      setRevokeTarget(null);
    }
  };

  const handleExtend = (newEndDate: string) => {
    if (extendTarget) {
      extendMutation.mutate({ delegationId: extendTarget.id, newEndDate });
      setExtendTarget(null);
    }
  };

  // Count pending received delegations
  const pendingReceivedCount =
    receivedData?.delegations.filter(
      (d) => d.status === DelegationStatus.PENDING
    ).length || 0;

  // Count active delegations
  const activeGivenCount =
    givenData?.delegations.filter((d) => d.status === DelegationStatus.ACTIVE)
      .length || 0;
  const activeReceivedCount =
    receivedData?.delegations.filter(
      (d) => d.status === DelegationStatus.ACTIVE
    ).length || 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Users className="h-6 w-6" />
            Vertretungen
          </h1>
          <p className="text-muted-foreground mt-1">
            Verwalten Sie Ihre Vertretungsregelungen
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isLoading}
          >
            <RefreshCw
              className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`}
            />
            Aktualisieren
          </Button>
          <CreateDelegationDialog
            onSubmit={handleCreate}
            isLoading={createMutation.isPending}
          />
        </div>
      </div>

      {/* Status Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="p-3 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
                <ArrowUpRight className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold">{activeGivenCount}</p>
                <p className="text-sm text-muted-foreground">
                  Aktive Vertretungen vergeben
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="p-3 rounded-full bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400">
                <ArrowDownLeft className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold">{activeReceivedCount}</p>
                <p className="text-sm text-muted-foreground">
                  Aktive Vertretungen erhalten
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div
                className={`p-3 rounded-full ${
                  pendingReceivedCount > 0
                    ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400'
                    : 'bg-muted text-muted-foreground'
                }`}
              >
                <AlertCircle className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold">{pendingReceivedCount}</p>
                <p className="text-sm text-muted-foreground">
                  Offene Anfragen
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Info Alert */}
      <Alert>
        <Info className="h-4 w-4" />
        <AlertTitle>Hinweis zur Vertretung</AlertTitle>
        <AlertDescription>
          Vertretungen müssen vom Vertreter angenommen werden, bevor sie aktiv
          werden. Ausnahme: Notfall-Vertretungen sind sofort aktiv. Sie können
          Ihre Vertretungen jederzeit widerrufen.
        </AlertDescription>
      </Alert>

      {/* Tabs */}
      <Tabs defaultValue="given" className="space-y-4">
        <TabsList>
          <TabsTrigger value="given" className="flex items-center gap-2">
            <ArrowUpRight className="h-4 w-4" />
            Vergeben
            {activeGivenCount > 0 && (
              <Badge variant="secondary" className="ml-1">
                {activeGivenCount}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="received" className="flex items-center gap-2">
            <ArrowDownLeft className="h-4 w-4" />
            Erhalten
            {pendingReceivedCount > 0 && (
              <Badge variant="default" className="ml-1">
                {pendingReceivedCount}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* Given Delegations Tab */}
        <TabsContent value="given" className="space-y-4">
          {isLoadingGiven ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <Card key={i}>
                  <CardContent className="p-4">
                    <div className="flex items-start gap-4">
                      <Skeleton className="h-10 w-10 rounded-lg" />
                      <div className="flex-1 space-y-2">
                        <Skeleton className="h-5 w-40" />
                        <Skeleton className="h-4 w-full" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : givenData && givenData.delegations.length > 0 ? (
            <div className="space-y-4">
              {givenData.delegations.map((delegation) => (
                <DelegationCard
                  key={delegation.id}
                  delegation={delegation}
                  direction="given"
                  currentUserId={CURRENT_USER_ID}
                  onRevoke={(id) => setRevokeTarget(id)}
                  onExtend={(id) => {
                    const d = givenData.delegations.find((del) => del.id === id);
                    if (d) setExtendTarget(d);
                  }}
                  isLoading={isAnyMutating}
                />
              ))}
            </div>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <ArrowUpRight className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <h3 className="text-lg font-semibold mb-2">
                  Keine Vertretungen vergeben
                </h3>
                <p className="text-muted-foreground mb-4">
                  Sie haben noch keine Vertretungen eingerichtet.
                </p>
                <CreateDelegationDialog
                  onSubmit={handleCreate}
                  isLoading={createMutation.isPending}
                />
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Received Delegations Tab */}
        <TabsContent value="received" className="space-y-4">
          {isLoadingReceived ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <Card key={i}>
                  <CardContent className="p-4">
                    <div className="flex items-start gap-4">
                      <Skeleton className="h-10 w-10 rounded-lg" />
                      <div className="flex-1 space-y-2">
                        <Skeleton className="h-5 w-40" />
                        <Skeleton className="h-4 w-full" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : receivedData && receivedData.delegations.length > 0 ? (
            <div className="space-y-4">
              {receivedData.delegations.map((delegation) => (
                <DelegationCard
                  key={delegation.id}
                  delegation={delegation}
                  direction="received"
                  currentUserId={CURRENT_USER_ID}
                  onAccept={handleAccept}
                  onDecline={(id) => setDeclineTarget(id)}
                  isLoading={isAnyMutating}
                />
              ))}
            </div>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <ArrowDownLeft className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <h3 className="text-lg font-semibold mb-2">
                  Keine Vertretungen erhalten
                </h3>
                <p className="text-muted-foreground">
                  Sie haben keine offenen oder aktiven Vertretungsanfragen.
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Action Dialogs */}
      <DeclineDelegationDialog
        open={declineTarget !== null}
        onOpenChange={(open) => !open && setDeclineTarget(null)}
        onConfirm={handleDecline}
        isLoading={declineMutation.isPending}
      />

      <RevokeDelegationDialog
        open={revokeTarget !== null}
        onOpenChange={(open) => !open && setRevokeTarget(null)}
        onConfirm={handleRevoke}
        isLoading={revokeMutation.isPending}
      />

      <ExtendDelegationDialog
        open={extendTarget !== null}
        onOpenChange={(open) => !open && setExtendTarget(null)}
        currentEndDate={extendTarget?.end_date || ''}
        onConfirm={handleExtend}
        isLoading={extendMutation.isPending}
      />
    </div>
  );
}
