/**
 * Disaster Recovery Dashboard Page
 *
 * Zentrale Seite für Backup-Management und Disaster Recovery.
 *
 * Features:
 * 1. Backup Status Overview
 * 2. Automatische Restore-Tests (weekly)
 * 3. RTO/RPO Monitoring
 * 4. Backup-Integritäts-Checks
 * 5. Recovery Playbook Generator
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Shield,
  Database,
  Activity,
  CheckCircle2,
  BookOpen,
  PlayCircle,
  RefreshCw,
  AlertTriangle,
} from 'lucide-react';
import {
  useBackupStatus,
  useBackups,
  useRestoreTestHistory,
  useRTOMetrics,
  useValidateBackup,
  useValidateAllBackups,
  useCreateFullBackup,
  useRunRestoreTest,
} from './hooks';
import {
  BackupStatusCard,
  RestoreTestsPanel,
  BackupValidationPanel,
  RTOMonitoringCard,
  RecoveryPlaybook,
} from './components';
import { useToast } from '@/hooks/use-toast';

type TabValue = 'overview' | 'tests' | 'validation' | 'playbook';

export function DisasterRecoveryPage() {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<TabValue>('overview');

  // Queries
  const { data: status, isLoading: statusLoading } = useBackupStatus();
  const { data: backups = [], isLoading: backupsLoading } = useBackups();
  const { data: testHistory, isLoading: testsLoading } = useRestoreTestHistory();
  const { data: rtoMetrics, isLoading: metricsLoading } = useRTOMetrics();

  // Mutations
  const validateBackupMutation = useValidateBackup();
  const validateAllMutation = useValidateAllBackups();
  const createBackupMutation = useCreateFullBackup();
  const runTestMutation = useRunRestoreTest();

  // Handlers
  const handleValidateBackup = async (backupName: string) => {
    try {
      await validateBackupMutation.mutateAsync(backupName);
      toast({
        title: 'Validierung erfolgreich',
        description: `Backup "${backupName}" wurde validiert.`,
      });
    } catch (error) {
      toast({
        title: 'Validierung fehlgeschlagen',
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const handleValidateAll = async () => {
    try {
      await validateAllMutation.mutateAsync();
      toast({
        title: 'Alle Backups validiert',
        description: 'Die Validierung aller Backups wurde gestartet.',
      });
    } catch (error) {
      toast({
        title: 'Validierung fehlgeschlagen',
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const handleCreateBackup = async () => {
    try {
      const result = await createBackupMutation.mutateAsync();
      toast({
        title: 'Backup erstellt',
        description: result.message,
      });
    } catch (error) {
      toast({
        title: 'Backup fehlgeschlagen',
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const handleRunTest = async () => {
    try {
      await runTestMutation.mutateAsync({ test_type: 'full', dry_run: false });
      toast({
        title: 'Restore-Test gestartet',
        description: 'Der vollständige Restore-Test wurde gestartet.',
      });
    } catch (error) {
      toast({
        title: 'Test fehlgeschlagen',
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  // Compute stats
  const isSystemHealthy =
    status?.service_aktiv &&
    status?.encryption_aktiv &&
    (rtoMetrics?.rto_compliance_rate ?? 0) >= 0.9 &&
    (rtoMetrics?.rpo_compliance_rate ?? 0) >= 0.9;

  const validBackups = backups.filter((b) => b.validation_status === 'success').length;
  const totalBackups = backups.length;
  const backupHealthPercent = totalBackups > 0 ? (validBackups / totalBackups) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Shield className="h-6 w-6" />
            Disaster Recovery
          </h1>
          <p className="text-muted-foreground">
            Backup-Management, Restore-Tests und Recovery-Planung
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={handleCreateBackup}
            disabled={createBackupMutation.isPending}
          >
            {createBackupMutation.isPending ? (
              <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Database className="h-4 w-4 mr-2" />
            )}
            Vollsicherung
          </Button>
          <Button onClick={handleRunTest} disabled={runTestMutation.isPending}>
            {runTestMutation.isPending ? (
              <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <PlayCircle className="h-4 w-4 mr-2" />
            )}
            Restore-Test
          </Button>
        </div>
      </div>

      {/* System Health Alert */}
      {!statusLoading && !isSystemHealthy && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>System-Warnung</AlertTitle>
          <AlertDescription>
            Das Disaster-Recovery-System meldet Probleme. Bitte überprüfen Sie die Details.
          </AlertDescription>
        </Alert>
      )}

      {/* Overview Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-muted-foreground mb-1">System-Status</div>
                <div className="text-2xl font-bold">
                  {isSystemHealthy ? 'Gesund' : 'Warnung'}
                </div>
              </div>
              {isSystemHealthy ? (
                <CheckCircle2 className="h-8 w-8 text-green-600" />
              ) : (
                <AlertTriangle className="h-8 w-8 text-red-600" />
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-muted-foreground mb-1">Backups</div>
                <div className="text-2xl font-bold">
                  {validBackups}/{totalBackups}
                </div>
              </div>
              <Database className="h-8 w-8 text-muted-foreground" />
            </div>
            <div className="mt-2 h-2 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 transition-all"
                style={{ width: `${backupHealthPercent}%` }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-muted-foreground mb-1">RTO Compliance</div>
                <div className="text-2xl font-bold">
                  {((rtoMetrics?.rto_compliance_rate ?? 0) * 100).toFixed(0)}%
                </div>
              </div>
              <Activity className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-muted-foreground mb-1">Tests (90 Tage)</div>
                <div className="text-2xl font-bold">
                  {testHistory?.total_tests ?? 0}
                </div>
              </div>
              <PlayCircle className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as TabValue)}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <Database className="h-4 w-4" />
            Übersicht
          </TabsTrigger>
          <TabsTrigger value="tests" className="flex items-center gap-2">
            <PlayCircle className="h-4 w-4" />
            Restore-Tests
          </TabsTrigger>
          <TabsTrigger value="validation" className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Validierung
          </TabsTrigger>
          <TabsTrigger value="playbook" className="flex items-center gap-2">
            <BookOpen className="h-4 w-4" />
            Recovery-Playbook
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <BackupStatusCard status={status} isLoading={statusLoading} />
            <RTOMonitoringCard metrics={rtoMetrics} isLoading={metricsLoading} />
          </div>
        </TabsContent>

        {/* Tests Tab */}
        <TabsContent value="tests">
          <RestoreTestsPanel
            history={testHistory}
            isLoading={testsLoading}
            onRunTest={handleRunTest}
            isRunningTest={runTestMutation.isPending}
          />
        </TabsContent>

        {/* Validation Tab */}
        <TabsContent value="validation">
          <BackupValidationPanel
            backups={backups}
            isLoading={backupsLoading}
            onValidate={handleValidateBackup}
            onValidateAll={handleValidateAll}
            isValidating={validateAllMutation.isPending}
          />
        </TabsContent>

        {/* Playbook Tab */}
        <TabsContent value="playbook">
          <RecoveryPlaybook />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default DisasterRecoveryPage;
