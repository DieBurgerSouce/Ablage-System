/**
 * WorkflowVersionsPage - Workflow-Versionierung Dashboard
 *
 * Hauptseite für Workflow-Versionsverwaltung:
 * - Versions-Liste mit Status
 * - Diff-Ansicht
 * - A/B Testing
 * - Rollback-Funktionalitaet
 */

import { useState } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import {
  GitBranch,
  Plus,
  RotateCcw,
  FlaskConical,
  ArrowLeft,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { VersionList } from './components/VersionList';
import { VersionDiff } from './components/VersionDiff';
import { ABTestCard } from './components/ABTestCard';
import { RollbackDialog } from './components/RollbackDialog';
import { CreateVersionDialog } from './components/CreateVersionDialog';
import {
  useWorkflowVersions,
  useActiveVersion,
  useABTests,
} from './hooks';
import type { WorkflowVersion } from './types/version-types';

export function WorkflowVersionsPage() {
  const { workflowId } = useParams({ from: '/workflows/$workflowId/versions' });
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState('versions');
  const [selectedVersion, setSelectedVersion] = useState<WorkflowVersion | null>(null);
  const [compareVersions, setCompareVersions] = useState<{
    versionA: WorkflowVersion;
    versionB: WorkflowVersion;
  } | null>(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showRollbackDialog, setShowRollbackDialog] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<WorkflowVersion | null>(null);

  // Queries
  const {
    data: versions,
    isLoading: versionsLoading,
    error: versionsError,
  } = useWorkflowVersions(workflowId);

  const { data: activeVersionData, isLoading: activeVersionLoading } = useActiveVersion(workflowId);

  // Die Versions-API liefert { items, total } — hier die eigentliche Liste.
  const versionItems = versions?.items;
  const { data: abTests, isLoading: abTestLoading } = useABTests(workflowId);

  // Workflow-Name aus aktiver Version oder Versions-Liste ableiten
  const workflow = activeVersionData ? {
    name: activeVersionData.definition?.name ?? `Workflow ${workflowId.slice(0, 8)}`,
  } : (versionItems?.[0] ? {
    name: versionItems[0].definition?.name ?? `Workflow ${workflowId.slice(0, 8)}`,
  } : null);

  // Aktiver AB-Test aus Liste filtern
  const activeABTest = abTests?.find(test => test.status === 'running') ?? null;

  const isLoading = versionsLoading || activeVersionLoading;

  // Handler
  const handleSelectVersion = (version: WorkflowVersion) => {
    setSelectedVersion(version);
  };

  const handleCompareVersions = (versionA: WorkflowVersion, versionB: WorkflowVersion) => {
    setCompareVersions({ versionA, versionB });
    setActiveTab('diff');
  };

  const handleRollback = (version: WorkflowVersion) => {
    setRollbackTarget(version);
    setShowRollbackDialog(true);
  };

  const handleRollbackComplete = () => {
    setShowRollbackDialog(false);
    setRollbackTarget(null);
  };

  const handleVersionCreated = () => {
    setShowCreateDialog(false);
  };

  // Stats berechnen
  const activeVersion = versionItems?.find((v) => v.is_active);
  const draftVersions = versionItems?.filter((v) => v.status === 'draft') ?? [];
  const totalExecutions = versionItems?.reduce((sum, v) => sum + v.execution_count, 0) ?? 0;
  const avgSuccessRate =
    versionItems && versionItems.length > 0
      ? versionItems.reduce((sum, v) => sum + v.success_rate * v.execution_count, 0) /
        (totalExecutions || 1)
      : 0;

  if (isLoading) {
    return (
      <div className="space-y-6 p-8">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (versionsError) {
    return (
      <div className="p-8">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Fehler beim Laden</AlertTitle>
          <AlertDescription>
            Die Workflow-Versionen konnten nicht geladen werden.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-6 p-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate({ to: '/workflows/$workflowId', params: { workflowId } })}
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
                <GitBranch className="h-8 w-8" />
                Versionen
              </h1>
              <p className="text-muted-foreground mt-1">
                {workflow?.name ?? 'Workflow'} - Versionsverwaltung
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setShowCreateDialog(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Neue Version
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Versionen
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{versionItems?.length ?? 0}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {draftVersions.length} Entwürfe
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Aktive Version
              </CardTitle>
            </CardHeader>
            <CardContent>
              {activeVersion ? (
                <>
                  <p className="text-2xl font-bold">v{activeVersion.version}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {activeVersion.change_type}
                  </p>
                </>
              ) : (
                <p className="text-muted-foreground">Keine aktive Version</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Ausführungen (Gesamt)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{totalExecutions.toLocaleString('de-DE')}</p>
              <p className="text-xs text-muted-foreground mt-1">
                über alle Versionen
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Erfolgsrate (Ø)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                {avgSuccessRate >= 90 ? (
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                ) : avgSuccessRate >= 70 ? (
                  <AlertTriangle className="h-5 w-5 text-yellow-500" />
                ) : (
                  <AlertTriangle className="h-5 w-5 text-red-500" />
                )}
                <span className="text-2xl font-bold">{avgSuccessRate.toFixed(1)}%</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* A/B Test Warnung */}
        {activeABTest && (
          <Alert>
            <FlaskConical className="h-4 w-4" />
            <AlertTitle>A/B Test aktiv</AlertTitle>
            <AlertDescription>
              Aktuell läuft der A/B Test „{activeABTest.name}&ldquo;.
              Traffic-Verteilung:{' '}
              {100 - activeABTest.treatment_percentage}% /{' '}
              {activeABTest.treatment_percentage}%
            </AlertDescription>
          </Alert>
        )}

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="versions" className="flex items-center gap-2">
              <GitBranch className="h-4 w-4" />
              Versionen
            </TabsTrigger>
            <TabsTrigger value="diff" className="flex items-center gap-2">
              <RotateCcw className="h-4 w-4" />
              Vergleich
            </TabsTrigger>
            <TabsTrigger value="ab-test" className="flex items-center gap-2">
              <FlaskConical className="h-4 w-4" />
              A/B Testing
            </TabsTrigger>
          </TabsList>

          {/* Versions Tab */}
          <TabsContent value="versions">
            <Card>
              <CardHeader>
                <CardTitle>Alle Versionen</CardTitle>
                <CardDescription>
                  Verwalten Sie alle Versionen dieses Workflows. Klicken Sie auf eine
                  Version für Details.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <VersionList
                  versions={versionItems ?? []}
                  workflowId={workflowId}
                  isLoading={versionsLoading}
                  onSelectVersion={handleSelectVersion}
                  onCompareVersions={handleCompareVersions}
                  onRollback={handleRollback}
                  selectedVersionId={selectedVersion?.id}
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Diff Tab */}
          <TabsContent value="diff">
            <Card>
              <CardHeader>
                <CardTitle>Versions-Vergleich</CardTitle>
                <CardDescription>
                  Vergleichen Sie zwei Versionen, um Änderungen zu sehen.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {compareVersions ? (
                  <VersionDiff
                    workflowId={workflowId}
                    versionA={compareVersions.versionA}
                    versionB={compareVersions.versionB}
                  />
                ) : (
                  <div className="text-center py-12 text-muted-foreground">
                    <GitBranch className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>Wählen Sie zwei Versionen zum Vergleichen aus.</p>
                    <p className="text-sm mt-2">
                      Nutzen Sie das Kontextmenue in der Versionsliste oder den Vergleichsmodus.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* A/B Testing Tab */}
          <TabsContent value="ab-test">
            {abTestLoading ? (
              <div className="text-center py-12 text-muted-foreground">
                <p>A/B-Tests werden geladen …</p>
              </div>
            ) : activeABTest ? (
              <ABTestCard
                test={activeABTest}
                workflowId={workflowId}
                controlVersion={
                  versionItems?.find(
                    (v) => v.id === activeABTest.control_version_id
                  )?.version
                }
                treatmentVersion={
                  versionItems?.find(
                    (v) => v.id === activeABTest.treatment_version_id
                  )?.version
                }
              />
            ) : (
              <div className="text-center py-12 text-muted-foreground">
                <FlaskConical className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Kein aktiver A/B-Test fuer diesen Workflow.</p>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* Dialogs */}
      <CreateVersionDialog
        open={showCreateDialog}
        onOpenChange={(open) => {
          setShowCreateDialog(open);
          if (!open) handleVersionCreated();
        }}
        workflowId={workflowId}
        currentVersion={versionItems?.[0]?.version}
      />

      <RollbackDialog
        open={showRollbackDialog}
        onOpenChange={(open) => {
          setShowRollbackDialog(open);
          if (!open) handleRollbackComplete();
        }}
        workflowId={workflowId}
        targetVersion={rollbackTarget}
        currentActiveVersion={activeVersion}
      />
    </>
  );
}

export default WorkflowVersionsPage;
