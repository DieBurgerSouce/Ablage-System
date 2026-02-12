/**
 * WorkflowSimulator Component
 *
 * Dry-Run Simulationspanel für Workflows.
 * Zeigt Schritt-für-Schritt-Ausführung mit Testdaten.
 */

import { useState } from 'react';
import {
  Play,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  FileText,
  Zap,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';

type StepStatus = 'pending' | 'running' | 'passed' | 'failed' | 'skipped';

interface SimulationStep {
  id: string;
  name: string;
  type: 'trigger' | 'condition' | 'action' | 'delay' | 'branch';
  status: StepStatus;
  timestamp: string | null;
  duration: number | null;
  result: string | null;
  details: string | null;
}

interface SimulationInput {
  documentType: string;
  fileName: string;
  ocrConfidence: string;
  customData: string;
}

const INITIAL_STEPS: SimulationStep[] = [
  {
    id: '1',
    name: 'Trigger: Dokument hochgeladen',
    type: 'trigger',
    status: 'pending',
    timestamp: null,
    duration: null,
    result: null,
    details: null,
  },
  {
    id: '2',
    name: 'Bedingung: OCR Konfidenz prüfen',
    type: 'condition',
    status: 'pending',
    timestamp: null,
    duration: null,
    result: null,
    details: null,
  },
  {
    id: '3',
    name: 'Aktion: Dokument klassifizieren',
    type: 'action',
    status: 'pending',
    timestamp: null,
    duration: null,
    result: null,
    details: null,
  },
  {
    id: '4',
    name: 'Verzweigung: Nach Dokumenttyp',
    type: 'branch',
    status: 'pending',
    timestamp: null,
    duration: null,
    result: null,
    details: null,
  },
  {
    id: '5',
    name: 'Aktion: In Ordner verschieben',
    type: 'action',
    status: 'pending',
    timestamp: null,
    duration: null,
    result: null,
    details: null,
  },
];

const statusConfig: Record<
  StepStatus,
  { icon: React.ElementType; color: string; label: string }
> = {
  pending: { icon: Clock, color: 'text-muted-foreground', label: 'Ausstehend' },
  running: { icon: Loader2, color: 'text-blue-500', label: 'Läuft...' },
  passed: { icon: CheckCircle, color: 'text-green-500', label: 'Erfolgreich' },
  failed: { icon: XCircle, color: 'text-red-500', label: 'Fehlgeschlagen' },
  skipped: { icon: Clock, color: 'text-yellow-500', label: 'Übersprungen' },
};

interface WorkflowSimulatorProps {
  workflowId?: string;
}

export function WorkflowSimulator({ workflowId: _workflowId }: WorkflowSimulatorProps) {
  const [isRunning, setIsRunning] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [steps, setSteps] = useState<SimulationStep[]>(INITIAL_STEPS);
  const [inputOpen, setInputOpen] = useState(true);
  const [input, setInput] = useState<SimulationInput>({
    documentType: 'rechnung',
    fileName: 'Rechnung_2026_001.pdf',
    ocrConfidence: '92',
    customData: '',
  });

  const simulateStep = (
    stepIndex: number,
    allSteps: SimulationStep[]
  ): SimulationStep[] => {
    const updated = [...allSteps];
    const step = { ...updated[stepIndex] };
    const now = new Date();

    step.timestamp = now.toLocaleTimeString('de-DE', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      fractionalSecondDigits: 3,
    });

    const confidence = parseInt(input.ocrConfidence, 10) || 0;

    if (step.type === 'condition' && confidence < 70) {
      step.status = 'failed';
      step.duration = Math.random() * 50 + 10;
      step.result = 'Bedingung nicht erfüllt';
      step.details = `OCR Konfidenz ${confidence}% < 70% Schwellwert`;

      // Skip remaining steps
      for (let i = stepIndex + 1; i < updated.length; i++) {
        updated[i] = { ...updated[i], status: 'skipped' };
      }
    } else {
      step.status = 'passed';
      step.duration = Math.random() * 200 + 20;

      switch (step.type) {
        case 'trigger':
          step.result = 'Event empfangen';
          step.details = `Datei: ${input.fileName} (${input.documentType})`;
          break;
        case 'condition':
          step.result = 'Bedingung erfüllt';
          step.details = `OCR Konfidenz ${confidence}% >= 70% Schwellwert`;
          break;
        case 'action':
          step.result = 'Aktion ausgeführt';
          step.details = stepIndex === 2
            ? `Dokument als "${input.documentType}" klassifiziert`
            : `Verschoben nach /archiv/${input.documentType}/`;
          break;
        case 'branch':
          step.result = `Zweig: ${input.documentType}`;
          step.details = `Weiterleitung basierend auf Dokumenttyp`;
          break;
        default:
          step.result = 'Schritt abgeschlossen';
          break;
      }
    }

    updated[stepIndex] = step;
    return updated;
  };

  const handleStartSimulation = async () => {
    setIsRunning(true);
    setIsComplete(false);
    setInputOpen(false);

    let currentSteps = INITIAL_STEPS.map((s) => ({ ...s, status: 'pending' as StepStatus }));
    setSteps(currentSteps);

    for (let i = 0; i < currentSteps.length; i++) {
      // Mark current step as running
      currentSteps = currentSteps.map((s, idx) =>
        idx === i ? { ...s, status: 'running' as StepStatus } : s
      );
      setSteps([...currentSteps]);

      // Simulate processing delay
      await new Promise((resolve) => setTimeout(resolve, 600 + Math.random() * 400));

      // Complete the step
      currentSteps = simulateStep(i, currentSteps);
      setSteps([...currentSteps]);

      // If step failed or was skipped, stop
      if (currentSteps[i].status === 'failed') {
        break;
      }
    }

    setIsRunning(false);
    setIsComplete(true);
  };

  const handleReset = () => {
    setSteps(INITIAL_STEPS);
    setIsComplete(false);
    setInputOpen(true);
  };

  const allPassed = steps.every(
    (s) => s.status === 'passed' || s.status === 'skipped'
  );
  const hasFailed = steps.some((s) => s.status === 'failed');

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <Zap className="h-5 w-5" />
              Workflow-Simulation
            </CardTitle>
            <CardDescription>
              Testen Sie den Workflow mit Beispieldaten ohne echte Ausführung.
            </CardDescription>
          </div>
          <div className="flex gap-2">
            {isComplete && (
              <Button variant="outline" size="sm" onClick={handleReset}>
                <RotateCcw className="mr-2 h-4 w-4" />
                Zurücksetzen
              </Button>
            )}
            <Button
              size="sm"
              onClick={handleStartSimulation}
              disabled={isRunning}
            >
              {isRunning ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Simulation läuft...
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Simulation starten
                </>
              )}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Test Input Data */}
        <Collapsible open={inputOpen} onOpenChange={setInputOpen}>
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-between"
            >
              <span className="flex items-center gap-2">
                <FileText className="h-4 w-4" />
                Testdaten
              </span>
              {inputOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="sim-doctype">Dokumenttyp</Label>
                <Input
                  id="sim-doctype"
                  value={input.documentType}
                  onChange={(e) =>
                    setInput((prev) => ({ ...prev, documentType: e.target.value }))
                  }
                  disabled={isRunning}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="sim-filename">Dateiname</Label>
                <Input
                  id="sim-filename"
                  value={input.fileName}
                  onChange={(e) =>
                    setInput((prev) => ({ ...prev, fileName: e.target.value }))
                  }
                  disabled={isRunning}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="sim-confidence">OCR Konfidenz (%)</Label>
                <Input
                  id="sim-confidence"
                  type="number"
                  min="0"
                  max="100"
                  value={input.ocrConfidence}
                  onChange={(e) =>
                    setInput((prev) => ({
                      ...prev,
                      ocrConfidence: e.target.value,
                    }))
                  }
                  disabled={isRunning}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="sim-custom">Zusätzliche Daten</Label>
                <Input
                  id="sim-custom"
                  value={input.customData}
                  onChange={(e) =>
                    setInput((prev) => ({ ...prev, customData: e.target.value }))
                  }
                  placeholder="Optional"
                  disabled={isRunning}
                />
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>

        <Separator />

        {/* Step Execution Timeline */}
        <div className="space-y-1">
          {steps.map((step, index) => {
            const config = statusConfig[step.status];
            const Icon = config.icon;

            return (
              <div key={step.id} className="relative">
                {/* Connecting line */}
                {index < steps.length - 1 && (
                  <div
                    className={cn(
                      'absolute left-[19px] top-10 w-0.5 h-4',
                      step.status === 'passed'
                        ? 'bg-green-300'
                        : step.status === 'failed'
                          ? 'bg-red-300'
                          : 'bg-muted-foreground/20'
                    )}
                  />
                )}

                <div
                  className={cn(
                    'flex items-start gap-3 p-3 rounded-lg transition-colors',
                    step.status === 'running' && 'bg-blue-50 dark:bg-blue-950/20',
                    step.status === 'failed' && 'bg-red-50 dark:bg-red-950/20'
                  )}
                >
                  <div className="mt-0.5">
                    <Icon
                      className={cn(
                        'h-5 w-5',
                        config.color,
                        step.status === 'running' && 'animate-spin'
                      )}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-sm">{step.name}</span>
                      <div className="flex items-center gap-2 shrink-0">
                        {step.duration !== null && (
                          <span className="text-xs text-muted-foreground font-mono">
                            {step.duration.toFixed(0)}ms
                          </span>
                        )}
                        <Badge
                          variant={
                            step.status === 'passed'
                              ? 'outline'
                              : step.status === 'failed'
                                ? 'destructive'
                                : 'secondary'
                          }
                          className="text-xs"
                        >
                          {config.label}
                        </Badge>
                      </div>
                    </div>
                    {step.result && (
                      <p className="text-sm text-muted-foreground mt-1">
                        {step.result}
                      </p>
                    )}
                    {step.details && (
                      <p className="text-xs text-muted-foreground mt-0.5 font-mono">
                        {step.details}
                      </p>
                    )}
                    {step.timestamp && (
                      <p className="text-xs text-muted-foreground mt-1">
                        {step.timestamp}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Summary */}
        {isComplete && (
          <>
            <Separator />
            <div
              className={cn(
                'rounded-lg border p-4',
                allPassed && !hasFailed
                  ? 'border-green-500/50 bg-green-50 dark:bg-green-950/20'
                  : 'border-red-500/50 bg-red-50 dark:bg-red-950/20'
              )}
            >
              <div className="flex items-center gap-2">
                {allPassed && !hasFailed ? (
                  <>
                    <CheckCircle className="h-5 w-5 text-green-600" />
                    <span className="font-medium text-green-800 dark:text-green-200">
                      Simulation erfolgreich abgeschlossen
                    </span>
                  </>
                ) : (
                  <>
                    <XCircle className="h-5 w-5 text-red-600" />
                    <span className="font-medium text-red-800 dark:text-red-200">
                      Simulation mit Fehlern abgeschlossen
                    </span>
                  </>
                )}
              </div>
              <p className="text-sm text-muted-foreground mt-2">
                {steps.filter((s) => s.status === 'passed').length} von{' '}
                {steps.length} Schritten erfolgreich
                {steps.filter((s) => s.status === 'skipped').length > 0 &&
                  `, ${steps.filter((s) => s.status === 'skipped').length} übersprungen`}
              </p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default WorkflowSimulator;
