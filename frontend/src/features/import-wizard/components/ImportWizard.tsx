/**
 * Import Wizard
 *
 * Multi-step wizard for guided import configuration and execution
 */

import { useState } from 'react';
import {
  Mail,
  Folder,
  FileSpreadsheet,
  ChevronRight,
  ChevronLeft,
  CheckCircle,
  AlertTriangle,
  Play,
  Loader2,
  FileText,
  Info,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

import {
  useImportSources,
  useEmailPreview,
  useFolderPreview,
  useStartImport,
} from '../api/wizard-api';
import { emailConfigService, folderConfigService, importRulesService } from '@/features/imports/api/imports-api';
import type { EmailConfigListItem, FolderConfigListItem } from '@/features/imports/types/import-types';
import { useQuery } from '@tanstack/react-query';

// ==================== Types ====================

type SourceType = 'email' | 'folder' | 'csv' | null;
type WizardStep = 1 | 2 | 3 | 4 | 5;

interface WizardState {
  currentStep: WizardStep;
  selectedSource: SourceType;
  selectedConfigId: string | null;
  applyRules: boolean;
}

// ==================== Main Component ====================

export function ImportWizard() {
  const [state, setState] = useState<WizardState>({
    currentStep: 1,
    selectedSource: null,
    selectedConfigId: null,
    applyRules: true,
  });

  const handleSourceSelect = (sourceType: SourceType) => {
    setState((prev) => ({
      ...prev,
      selectedSource: sourceType,
      currentStep: 2,
    }));
  };

  const handleConfigSelect = (configId: string) => {
    setState((prev) => ({
      ...prev,
      selectedConfigId: configId,
      currentStep: 3,
    }));
  };

  const handleBack = () => {
    setState((prev) => ({
      ...prev,
      currentStep: Math.max(1, prev.currentStep - 1) as WizardStep,
    }));
  };

  const handleNext = () => {
    setState((prev) => ({
      ...prev,
      currentStep: Math.min(5, prev.currentStep + 1) as WizardStep,
    }));
  };

  return (
    <div className="space-y-6">
      {/* Stepper */}
      <WizardStepper currentStep={state.currentStep} />

      {/* Step Content */}
      <div className="min-h-[400px]">
        {state.currentStep === 1 && (
          <Step1SourceSelection onSelect={handleSourceSelect} />
        )}
        {state.currentStep === 2 && state.selectedSource && (
          <Step2Configuration
            sourceType={state.selectedSource}
            onSelect={handleConfigSelect}
            onBack={handleBack}
          />
        )}
        {state.currentStep === 3 && state.selectedConfigId && state.selectedSource && (
          <Step3Preview
            sourceType={state.selectedSource}
            configId={state.selectedConfigId}
            onNext={handleNext}
            onBack={handleBack}
          />
        )}
        {state.currentStep === 4 && (
          <Step4Rules
            applyRules={state.applyRules}
            onToggleRules={(apply) => setState((prev) => ({ ...prev, applyRules: apply }))}
            onNext={handleNext}
            onBack={handleBack}
          />
        )}
        {state.currentStep === 5 && state.selectedConfigId && state.selectedSource && (
          <Step5Execute
            sourceType={state.selectedSource}
            configId={state.selectedConfigId}
            applyRules={state.applyRules}
            onBack={handleBack}
          />
        )}
      </div>
    </div>
  );
}

// ==================== Stepper Component ====================

interface WizardStepperProps {
  currentStep: WizardStep;
}

function WizardStepper({ currentStep }: WizardStepperProps) {
  const steps = [
    { number: 1, label: 'Quelle wählen' },
    { number: 2, label: 'Konfiguration' },
    { number: 3, label: 'Vorschau' },
    { number: 4, label: 'Regeln' },
    { number: 5, label: 'Import starten' },
  ];

  return (
    <div className="flex items-center justify-between">
      {steps.map((step, index) => (
        <div key={step.number} className="flex items-center flex-1">
          <div className="flex items-center">
            <div
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-full border-2 text-sm font-semibold',
                currentStep >= step.number
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-muted bg-background text-muted-foreground'
              )}
            >
              {currentStep > step.number ? (
                <CheckCircle className="h-5 w-5" />
              ) : (
                step.number
              )}
            </div>
            <div className="ml-2 hidden sm:block">
              <p
                className={cn(
                  'text-sm font-medium',
                  currentStep >= step.number ? 'text-foreground' : 'text-muted-foreground'
                )}
              >
                {step.label}
              </p>
            </div>
          </div>
          {index < steps.length - 1 && (
            <div className="flex-1 mx-4">
              <div
                className={cn(
                  'h-0.5',
                  currentStep > step.number ? 'bg-primary' : 'bg-muted'
                )}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ==================== Step 1: Source Selection ====================

interface Step1Props {
  onSelect: (sourceType: SourceType) => void;
}

function Step1SourceSelection({ onSelect }: Step1Props) {
  const { data: sources, isLoading } = useImportSources();

  if (isLoading) {
    return <Skeleton className="h-[400px]" />;
  }

  const getIcon = (iconName: string) => {
    switch (iconName) {
      case 'mail':
        return <Mail className="h-12 w-12" />;
      case 'folder':
        return <Folder className="h-12 w-12" />;
      case 'file-spreadsheet':
        return <FileSpreadsheet className="h-12 w-12" />;
      default:
        return <FileText className="h-12 w-12" />;
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Import-Quelle wählen</h2>
        <p className="text-muted-foreground">
          Wählen Sie die Art der Dokumente, die Sie importieren möchten.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {sources?.map((source) => (
          <Card
            key={source.type}
            className="cursor-pointer transition-all hover:shadow-lg hover:border-primary"
            onClick={() => onSelect(source.type)}
          >
            <CardHeader className="text-center">
              <div className="flex justify-center mb-4 text-primary">
                {getIcon(source.icon)}
              </div>
              <CardTitle>{source.label}</CardTitle>
              <CardDescription className="text-sm">
                {source.description}
              </CardDescription>
            </CardHeader>
            <CardContent className="text-center">
              <Button variant="outline" className="w-full">
                Auswählen
                <ChevronRight className="ml-2 h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ==================== Step 2: Configuration Selection ====================

interface Step2Props {
  sourceType: SourceType;
  onSelect: (configId: string) => void;
  onBack: () => void;
}

function Step2Configuration({ sourceType, onSelect, onBack }: Step2Props) {
  const { data: emailConfigs, isLoading: loadingEmail } = useQuery({
    queryKey: ['email-configs'],
    queryFn: emailConfigService.listConfigs,
    enabled: sourceType === 'email',
  });

  const { data: folderConfigs, isLoading: loadingFolder } = useQuery({
    queryKey: ['folder-configs'],
    queryFn: folderConfigService.listConfigs,
    enabled: sourceType === 'folder',
  });

  const isLoading = loadingEmail || loadingFolder;
  const configs = sourceType === 'email' ? emailConfigs : folderConfigs;

  if (isLoading) {
    return <Skeleton className="h-[400px]" />;
  }

  if (sourceType === 'csv') {
    return (
      <div>
        <div className="mb-6">
          <h2 className="text-2xl font-bold">CSV/Lexware Import</h2>
          <p className="text-muted-foreground">
            CSV-Import ist noch nicht über den Wizard verfügbar.
          </p>
        </div>
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Info</AlertTitle>
          <AlertDescription>
            Nutzen Sie den direkten Lexware-Import über das Lexware-Menü.
          </AlertDescription>
        </Alert>
        <div className="mt-6">
          <Button variant="outline" onClick={onBack}>
            <ChevronLeft className="mr-2 h-4 w-4" />
            Zurück
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Konfiguration wählen</h2>
        <p className="text-muted-foreground">
          Wählen Sie eine bestehende {sourceType === 'email' ? 'E-Mail-' : 'Ordner-'}
          Konfiguration oder erstellen Sie eine neue.
        </p>
      </div>

      {configs && configs.length > 0 ? (
        <div className="grid gap-4">
          {configs.map((config) => (
            <ConfigCard
              key={config.id}
              config={config}
              sourceType={sourceType}
              onSelect={() => onSelect(config.id)}
            />
          ))}
        </div>
      ) : (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Keine Konfigurationen gefunden</AlertTitle>
          <AlertDescription>
            Erstellen Sie zunächst eine {sourceType === 'email' ? 'E-Mail-' : 'Ordner-'}
            Konfiguration in den Import-Einstellungen.
          </AlertDescription>
        </Alert>
      )}

      <div className="mt-6 flex gap-2">
        <Button variant="outline" onClick={onBack}>
          <ChevronLeft className="mr-2 h-4 w-4" />
          Zurück
        </Button>
      </div>
    </div>
  );
}

interface ConfigCardProps {
  config: EmailConfigListItem | FolderConfigListItem;
  sourceType: 'email' | 'folder';
  onSelect: () => void;
}

function ConfigCard({ config, sourceType, onSelect }: ConfigCardProps) {
  const isEmail = sourceType === 'email';
  const status = isEmail
    ? (config as EmailConfigListItem).connectionStatus
    : (config as FolderConfigListItem).watcherStatus;

  const getStatusBadge = () => {
    const statusMap = {
      connected: { label: 'Verbunden', variant: 'default' as const },
      running: { label: 'Läuft', variant: 'default' as const },
      disconnected: { label: 'Getrennt', variant: 'secondary' as const },
      stopped: { label: 'Gestoppt', variant: 'secondary' as const },
      error: { label: 'Fehler', variant: 'destructive' as const },
      unknown: { label: 'Unbekannt', variant: 'outline' as const },
    };

    const statusInfo = statusMap[status] || statusMap.unknown;
    return <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>;
  };

  return (
    <Card className="cursor-pointer transition-all hover:shadow-md" onClick={onSelect}>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <CardTitle className="text-lg">{config.name}</CardTitle>
            <CardDescription className="mt-1">
              {isEmail
                ? `${(config as EmailConfigListItem).imapServer} - ${(config as EmailConfigListItem).imapFolder}`
                : (config as FolderConfigListItem).watchPath}
            </CardDescription>
          </div>
          {getStatusBadge()}
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{config.totalDocumentsCreated} Dokumente erstellt</span>
          {config.isActive ? (
            <Badge variant="outline" className="text-green-600">
              Aktiv
            </Badge>
          ) : (
            <Badge variant="outline">Inaktiv</Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Step 3: Preview ====================

interface Step3Props {
  sourceType: 'email' | 'folder';
  configId: string;
  onNext: () => void;
  onBack: () => void;
}

function Step3Preview({ sourceType, configId, onNext, onBack }: Step3Props) {
  const emailPreview = useEmailPreview(sourceType === 'email' ? configId : null);
  const folderPreview = useFolderPreview(sourceType === 'folder' ? configId : null);

  const preview = sourceType === 'email' ? emailPreview : folderPreview;
  const { data, isLoading, error } = preview;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-[200px]" />
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Fehler beim Laden der Vorschau</AlertTitle>
          <AlertDescription>{(error as Error).message}</AlertDescription>
        </Alert>
        <div className="mt-6 flex gap-2">
          <Button variant="outline" onClick={onBack}>
            <ChevronLeft className="mr-2 h-4 w-4" />
            Zurück
          </Button>
        </div>
      </div>
    );
  }

  const hasWarnings = data && data.warnings.length > 0;
  const hasItems = data && data.itemCount > 0;

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Import-Vorschau</h2>
        <p className="text-muted-foreground">
          Überprüfen Sie die zu importierenden Elemente.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3 mb-6">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Elemente gefunden</CardDescription>
            <CardTitle className="text-2xl">{data?.itemCount || 0}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Gesamtgröße</CardDescription>
            <CardTitle className="text-2xl">
              {data?.totalSize ? `${(data.totalSize / 1024 / 1024).toFixed(1)} MB` : '0 MB'}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Geschätzte Dauer</CardDescription>
            <CardTitle className="text-2xl">{data?.estimatedDuration || '-'}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Warnings */}
      {hasWarnings && (
        <Alert className="mb-6">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Warnungen</AlertTitle>
          <AlertDescription>
            <ul className="list-disc list-inside mt-2">
              {data?.warnings.map((warning, i) => (
                <li key={i}>{warning}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {/* Sample Items */}
      {data && data.sampleItems.length > 0 && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">Beispiel-Elemente</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {data.sampleItems.map((item, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between border-b pb-2 last:border-0"
                >
                  <div className="flex-1">
                    <p className="text-sm font-medium">{item.filename}</p>
                    <p className="text-xs text-muted-foreground">{item.source}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm">{(item.size / 1024).toFixed(1)} KB</p>
                    <Badge variant="outline" className="text-xs">
                      {item.type}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Ready Indicator */}
      {hasItems && (
        <Alert className="border-green-500 bg-green-50 dark:bg-green-950 mb-6">
          <CheckCircle className="h-4 w-4 text-green-600" />
          <AlertTitle className="text-green-700 dark:text-green-300">
            Bereit zum Import
          </AlertTitle>
          <AlertDescription className="text-green-600 dark:text-green-400">
            {data?.itemCount} Elemente können importiert werden.
          </AlertDescription>
        </Alert>
      )}

      {/* Navigation */}
      <div className="flex gap-2">
        <Button variant="outline" onClick={onBack}>
          <ChevronLeft className="mr-2 h-4 w-4" />
          Zurück
        </Button>
        <Button onClick={onNext} disabled={!hasItems}>
          Weiter
          <ChevronRight className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

// ==================== Step 4: Rules ====================

interface Step4Props {
  applyRules: boolean;
  onToggleRules: (apply: boolean) => void;
  onNext: () => void;
  onBack: () => void;
}

function Step4Rules({ applyRules, onToggleRules, onNext, onBack }: Step4Props) {
  const { data: rules, isLoading } = useQuery({
    queryKey: ['import-rules'],
    queryFn: importRulesService.listRules,
  });

  const activeRules = rules?.filter((r) => r.isActive) || [];

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Import-Regeln</h2>
        <p className="text-muted-foreground">
          Automatische Regeln können beim Import angewendet werden.
        </p>
      </div>

      {isLoading ? (
        <Skeleton className="h-[200px]" />
      ) : (
        <>
          <Card className="mb-6">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">Regeln anwenden</CardTitle>
                  <CardDescription>
                    {activeRules.length} aktive Regel(n) verfügbar
                  </CardDescription>
                </div>
                <Button
                  variant={applyRules ? 'default' : 'outline'}
                  onClick={() => onToggleRules(!applyRules)}
                >
                  {applyRules ? 'Aktiviert' : 'Deaktiviert'}
                </Button>
              </div>
            </CardHeader>
            {applyRules && activeRules.length > 0 && (
              <CardContent>
                <div className="space-y-2">
                  {activeRules.slice(0, 5).map((rule) => (
                    <div
                      key={rule.id}
                      className="flex items-center justify-between border-b pb-2 last:border-0"
                    >
                      <div>
                        <p className="text-sm font-medium">{rule.name}</p>
                        <p className="text-xs text-muted-foreground">
                          Priorität: {rule.priority}
                        </p>
                      </div>
                      <Badge variant="outline">{rule.matchCount} Treffer</Badge>
                    </div>
                  ))}
                  {activeRules.length > 5 && (
                    <p className="text-xs text-muted-foreground text-center pt-2">
                      ... und {activeRules.length - 5} weitere
                    </p>
                  )}
                </div>
              </CardContent>
            )}
          </Card>

          {activeRules.length === 0 && (
            <Alert>
              <Info className="h-4 w-4" />
              <AlertTitle>Keine aktiven Regeln</AlertTitle>
              <AlertDescription>
                Sie können Regeln in den Import-Einstellungen konfigurieren.
              </AlertDescription>
            </Alert>
          )}
        </>
      )}

      {/* Navigation */}
      <div className="flex gap-2 mt-6">
        <Button variant="outline" onClick={onBack}>
          <ChevronLeft className="mr-2 h-4 w-4" />
          Zurück
        </Button>
        <Button onClick={onNext}>
          Weiter
          <ChevronRight className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

// ==================== Step 5: Execute ====================

interface Step5Props {
  sourceType: 'email' | 'folder';
  configId: string;
  applyRules: boolean;
  onBack: () => void;
}

function Step5Execute({ sourceType, configId, applyRules, onBack }: Step5Props) {
  const [started, setStarted] = useState(false);
  const startImport = useStartImport();

  const handleStart = () => {
    setStarted(true);
    startImport.mutate({
      configId,
      sourceType,
    });
  };

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Import starten</h2>
        <p className="text-muted-foreground">Bestätigen Sie den Import-Vorgang.</p>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Zusammenfassung</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Quelle:</span>
            <span className="font-medium">
              {sourceType === 'email' ? 'E-Mail Import' : 'Ordner Import'}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Regeln:</span>
            <span className="font-medium">{applyRules ? 'Aktiviert' : 'Deaktiviert'}</span>
          </div>
        </CardContent>
      </Card>

      {/* Progress */}
      {started && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            {startImport.isPending && (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <p className="text-sm">Import wird gestartet...</p>
                </div>
                <Progress value={33} />
              </div>
            )}

            {startImport.isSuccess && (
              <Alert className="border-green-500 bg-green-50 dark:bg-green-950">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <AlertTitle className="text-green-700 dark:text-green-300">
                  Import gestartet
                </AlertTitle>
                <AlertDescription className="text-green-600 dark:text-green-400">
                  {startImport.data.message}
                  <br />
                  Task ID: <code className="text-xs">{startImport.data.taskId}</code>
                </AlertDescription>
              </Alert>
            )}

            {startImport.isError && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Fehler beim Import-Start</AlertTitle>
                <AlertDescription>{startImport.error.message}</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        <Button variant="outline" onClick={onBack} disabled={startImport.isPending}>
          <ChevronLeft className="mr-2 h-4 w-4" />
          Zurück
        </Button>
        {!started && (
          <Button onClick={handleStart}>
            <Play className="mr-2 h-4 w-4" />
            Import starten
          </Button>
        )}
        {startImport.isSuccess && (
          <Button asChild>
            <a href="/admin/imports/logs">Zu den Import-Logs</a>
          </Button>
        )}
      </div>
    </div>
  );
}
