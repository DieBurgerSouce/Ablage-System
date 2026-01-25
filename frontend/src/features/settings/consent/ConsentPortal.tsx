/**
 * ConsentPortal Component
 *
 * DSGVO Art. 6, 7 - Self-Service Einwilligungsverwaltung
 * Ermoeglicht Benutzern die Verwaltung ihrer Datenschutz-Einwilligungen.
 */

import { useState } from 'react';
import {
  Shield,
  CheckCircle2,
  AlertCircle,
  History,
  Info,
  RefreshCw,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { ConsentScopeCard } from './components/ConsentScopeCard';
import { ConsentHistoryTable } from './components/ConsentHistoryTable';
import { WithdrawConsentDialog } from './components/WithdrawConsentDialog';
import {
  useConsentStatus,
  useConsentHistory,
  useGrantConsent,
  useWithdrawConsent,
} from './hooks';
import type { ConsentScope } from './types';

export function ConsentPortal() {
  const [withdrawScope, setWithdrawScope] = useState<ConsentScope | null>(null);
  const [historyScope, setHistoryScope] = useState<ConsentScope | undefined>(undefined);

  // Queries
  const { data: consentStatus, isLoading: isLoadingStatus, refetch: refetchStatus } = useConsentStatus();
  const { data: consentHistory, isLoading: isLoadingHistory } = useConsentHistory(historyScope);

  // Mutations
  const grantMutation = useGrantConsent();
  const withdrawMutation = useWithdrawConsent();

  const handleToggle = (scope: ConsentScope, enabled: boolean) => {
    if (enabled) {
      // Grant consent
      grantMutation.mutate({
        scope,
        consent_given: true,
      });
    } else {
      // Show confirmation dialog before withdrawing
      setWithdrawScope(scope);
    }
  };

  const handleWithdrawConfirm = (scope: ConsentScope, reason?: string) => {
    withdrawMutation.mutate(
      { scope, reason },
      {
        onSuccess: () => setWithdrawScope(null),
      }
    );
  };

  const isAnyMutating = grantMutation.isPending || withdrawMutation.isPending;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Shield className="h-6 w-6" />
            Datenschutz-Einwilligungen
          </h1>
          <p className="text-muted-foreground mt-1">
            Verwalten Sie Ihre Einwilligungen gemaess DSGVO Art. 6 und 7
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetchStatus()}
          disabled={isLoadingStatus}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoadingStatus ? 'animate-spin' : ''}`} />
          Aktualisieren
        </Button>
      </div>

      {/* Status Overview */}
      {consentStatus && (
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="p-3 rounded-full bg-primary/10 text-primary">
                  <CheckCircle2 className="h-6 w-6" />
                </div>
                <div>
                  <p className="font-semibold text-lg">
                    {consentStatus.active_consents} von {consentStatus.total_consents}
                  </p>
                  <p className="text-sm text-muted-foreground">Einwilligungen erteilt</p>
                </div>
              </div>
              <div className="text-right text-sm text-muted-foreground">
                {consentStatus.nachricht}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Info Alert */}
      <Alert>
        <Info className="h-4 w-4" />
        <AlertTitle>Ihre Rechte nach DSGVO</AlertTitle>
        <AlertDescription>
          Sie koennen Ihre Einwilligungen jederzeit aendern oder widerrufen. Der Widerruf
          ist so einfach wie die Erteilung. Die Verarbeitung vor dem Widerruf bleibt
          rechtmaessig.
        </AlertDescription>
      </Alert>

      {/* Tabs */}
      <Tabs defaultValue="consents" className="space-y-4">
        <TabsList>
          <TabsTrigger value="consents" className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Einwilligungen
          </TabsTrigger>
          <TabsTrigger value="history" className="flex items-center gap-2">
            <History className="h-4 w-4" />
            Aenderungshistorie
          </TabsTrigger>
        </TabsList>

        {/* Consents Tab */}
        <TabsContent value="consents" className="space-y-4">
          {isLoadingStatus ? (
            <div className="space-y-4">
              {[1, 2, 3, 4].map((i) => (
                <Card key={i}>
                  <CardContent className="p-4">
                    <div className="flex items-start gap-4">
                      <Skeleton className="h-10 w-10 rounded-lg" />
                      <div className="flex-1 space-y-2">
                        <Skeleton className="h-5 w-40" />
                        <Skeleton className="h-4 w-full" />
                      </div>
                      <Skeleton className="h-6 w-12" />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : consentStatus ? (
            <div className="grid gap-4">
              {consentStatus.scopes.map((scopeInfo) => (
                <ConsentScopeCard
                  key={scopeInfo.scope}
                  scopeInfo={scopeInfo}
                  onToggle={handleToggle}
                  isLoading={isAnyMutating}
                />
              ))}
            </div>
          ) : (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Fehler</AlertTitle>
              <AlertDescription>
                Einwilligungen konnten nicht geladen werden. Bitte versuchen Sie es
                erneut.
              </AlertDescription>
            </Alert>
          )}
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <History className="h-5 w-5" />
                Aenderungshistorie
              </CardTitle>
              <CardDescription>
                Vollstaendige Uebersicht aller Aenderungen an Ihren Einwilligungen
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ConsentHistoryTable
                history={consentHistory?.history || []}
                isLoading={isLoadingHistory}
                selectedScope={historyScope}
                onScopeChange={setHistoryScope}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Withdraw Confirmation Dialog */}
      <WithdrawConsentDialog
        open={withdrawScope !== null}
        onOpenChange={(open) => !open && setWithdrawScope(null)}
        scope={withdrawScope}
        onConfirm={handleWithdrawConfirm}
        isLoading={withdrawMutation.isPending}
      />
    </div>
  );
}
