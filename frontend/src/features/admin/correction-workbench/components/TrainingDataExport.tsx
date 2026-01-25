/**
 * Training Data Export Component
 * Konfiguration und Ausfuehrung von Training-Daten-Exporten
 */

import { useState } from 'react';
import {
  Download,
  Settings2,
  FileJson,
  FileSpreadsheet,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  FolderOpen,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/hooks/use-toast';
import { useExportList, useExportTrainingData, useDeleteExport } from '../hooks';
import type { TrainingExportConfig, TrainingExportResult } from '../types';

const EXPORT_FORMATS = [
  {
    value: 'deepseek_jsonl',
    label: 'DeepSeek JSONL',
    description: 'Fuer DeepSeek-Janus Fine-Tuning',
    icon: FileJson,
  },
  {
    value: 'surya_hf',
    label: 'Surya HuggingFace',
    description: 'Fuer Surya OCR Training',
    icon: FileJson,
  },
  {
    value: 'generic_jsonl',
    label: 'Generic JSONL',
    description: 'Allgemeines JSONL-Format',
    icon: FileJson,
  },
  {
    value: 'csv',
    label: 'CSV',
    description: 'Tabellen-Format fuer Excel',
    icon: FileSpreadsheet,
  },
];

const SPLIT_STRATEGIES = [
  { value: 'random', label: 'Zufaellig', description: 'Zufaellige Verteilung' },
  {
    value: 'stratified',
    label: 'Stratifiziert',
    description: 'Gleichmaessige Typen-Verteilung',
  },
  {
    value: 'temporal',
    label: 'Zeitlich',
    description: 'Aeltere Daten fuer Training',
  },
];

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function TrainingDataExport() {
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [lastResult, setLastResult] = useState<TrainingExportResult | null>(null);
  const [config, setConfig] = useState<TrainingExportConfig>({
    format: 'deepseek_jsonl',
    splitRatio: { train: 0.8, val: 0.1, test: 0.1 },
    splitStrategy: 'random',
    verifiedOnly: true,
    minUmlautAccuracy: 0.9,
    includeMetadata: true,
  });

  const { toast } = useToast();
  const { data: exports, isLoading: exportsLoading, refetch } = useExportList();
  const exportMutation = useExportTrainingData();
  const deleteMutation = useDeleteExport();

  const handleSplitChange = (
    key: 'train' | 'val' | 'test',
    value: number
  ) => {
    const newRatio = { ...config.splitRatio };
    newRatio[key] = value;

    // Adjust other values to sum to 1.0
    const remaining = 1 - value;
    const otherKeys = (['train', 'val', 'test'] as const).filter((k) => k !== key);
    const currentOtherSum = otherKeys.reduce((sum, k) => sum + newRatio[k], 0);

    if (currentOtherSum > 0) {
      otherKeys.forEach((k) => {
        newRatio[k] = (newRatio[k] / currentOtherSum) * remaining;
      });
    } else {
      newRatio[otherKeys[0]] = remaining;
    }

    setConfig((prev) => ({ ...prev, splitRatio: newRatio }));
  };

  const handleExport = async () => {
    try {
      const result = await exportMutation.mutateAsync(config);
      setLastResult(result);
      setIsConfigOpen(false);

      if (result.success) {
        toast({
          title: 'Export erfolgreich',
          description: `${result.stats.totalSamples} Samples exportiert.`,
        });
        refetch();
      } else {
        toast({
          title: 'Export fehlgeschlagen',
          description: result.errors.join(', '),
          variant: 'destructive',
        });
      }
    } catch {
      toast({
        title: 'Fehler',
        description: 'Der Export konnte nicht gestartet werden.',
        variant: 'destructive',
      });
    }
  };

  const handleDelete = async (exportId: string) => {
    try {
      await deleteMutation.mutateAsync(exportId);
      toast({
        title: 'Export geloescht',
        description: 'Der Export wurde erfolgreich entfernt.',
      });
    } catch {
      toast({
        title: 'Fehler',
        description: 'Der Export konnte nicht geloescht werden.',
        variant: 'destructive',
      });
    }
  };

  const selectedFormat = EXPORT_FORMATS.find((f) => f.value === config.format);

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex-shrink-0 pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">
            Training-Daten Export
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => refetch()}
              disabled={exportsLoading}
            >
              <RefreshCw
                className={`h-4 w-4 ${exportsLoading ? 'animate-spin' : ''}`}
              />
            </Button>
            <Dialog open={isConfigOpen} onOpenChange={setIsConfigOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <Download className="h-4 w-4 mr-1" />
                  Neuer Export
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-md">
                <DialogHeader>
                  <DialogTitle>Export konfigurieren</DialogTitle>
                  <DialogDescription>
                    Konfigurieren Sie den Training-Daten-Export.
                  </DialogDescription>
                </DialogHeader>

                <div className="space-y-6 py-4">
                  {/* Format Selection */}
                  <div className="space-y-2">
                    <Label>Export-Format</Label>
                    <Select
                      value={config.format}
                      onValueChange={(value) =>
                        setConfig((prev) => ({
                          ...prev,
                          format: value as TrainingExportConfig['format'],
                        }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {EXPORT_FORMATS.map((format) => (
                          <SelectItem key={format.value} value={format.value}>
                            <div className="flex items-center gap-2">
                              <format.icon className="h-4 w-4" />
                              <div>
                                <p className="font-medium">{format.label}</p>
                                <p className="text-xs text-muted-foreground">
                                  {format.description}
                                </p>
                              </div>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <Separator />

                  {/* Split Ratio */}
                  <div className="space-y-4">
                    <Label>Daten-Aufteilung</Label>

                    <div className="space-y-3">
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span>Training</span>
                          <span>{(config.splitRatio.train * 100).toFixed(0)}%</span>
                        </div>
                        <Slider
                          value={[config.splitRatio.train]}
                          onValueChange={([v]) => handleSplitChange('train', v)}
                          min={0.5}
                          max={0.95}
                          step={0.05}
                        />
                      </div>

                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span>Validierung</span>
                          <span>{(config.splitRatio.val * 100).toFixed(0)}%</span>
                        </div>
                        <Slider
                          value={[config.splitRatio.val]}
                          onValueChange={([v]) => handleSplitChange('val', v)}
                          min={0.025}
                          max={0.25}
                          step={0.025}
                        />
                      </div>

                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span>Test</span>
                          <span>{(config.splitRatio.test * 100).toFixed(0)}%</span>
                        </div>
                        <Slider
                          value={[config.splitRatio.test]}
                          onValueChange={([v]) => handleSplitChange('test', v)}
                          min={0.025}
                          max={0.25}
                          step={0.025}
                        />
                      </div>
                    </div>

                    <Select
                      value={config.splitStrategy}
                      onValueChange={(value) =>
                        setConfig((prev) => ({
                          ...prev,
                          splitStrategy: value as TrainingExportConfig['splitStrategy'],
                        }))
                      }
                    >
                      <SelectTrigger className="h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {SPLIT_STRATEGIES.map((strategy) => (
                          <SelectItem key={strategy.value} value={strategy.value}>
                            {strategy.label} - {strategy.description}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <Separator />

                  {/* Options */}
                  <div className="space-y-4">
                    <Label>Optionen</Label>

                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium">Nur verifizierte</p>
                        <p className="text-xs text-muted-foreground">
                          Nur manuell verifizierte Samples
                        </p>
                      </div>
                      <Switch
                        checked={config.verifiedOnly}
                        onCheckedChange={(checked) =>
                          setConfig((prev) => ({ ...prev, verifiedOnly: checked }))
                        }
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium">Mit Metadaten</p>
                        <p className="text-xs text-muted-foreground">
                          Backend, Confidence, etc.
                        </p>
                      </div>
                      <Switch
                        checked={config.includeMetadata}
                        onCheckedChange={(checked) =>
                          setConfig((prev) => ({
                            ...prev,
                            includeMetadata: checked,
                          }))
                        }
                      />
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Min. Umlaut-Genauigkeit</span>
                        <span>{(config.minUmlautAccuracy * 100).toFixed(0)}%</span>
                      </div>
                      <Slider
                        value={[config.minUmlautAccuracy]}
                        onValueChange={([v]) =>
                          setConfig((prev) => ({ ...prev, minUmlautAccuracy: v }))
                        }
                        min={0.5}
                        max={1}
                        step={0.05}
                      />
                    </div>
                  </div>
                </div>

                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setIsConfigOpen(false)}
                  >
                    Abbrechen
                  </Button>
                  <Button
                    onClick={handleExport}
                    disabled={exportMutation.isPending}
                  >
                    {exportMutation.isPending ? (
                      <>
                        <RefreshCw className="h-4 w-4 mr-1 animate-spin" />
                        Exportiert...
                      </>
                    ) : (
                      <>
                        <Download className="h-4 w-4 mr-1" />
                        Exportieren
                      </>
                    )}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full">
          {/* Last Result Banner */}
          {lastResult && (
            <div
              className={`mx-4 mt-4 p-3 rounded-lg border ${
                lastResult.success
                  ? 'bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-800'
                  : 'bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800'
              }`}
            >
              <div className="flex items-start gap-2">
                {lastResult.success ? (
                  <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400 mt-0.5" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400 mt-0.5" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">
                    {lastResult.success
                      ? 'Export erfolgreich'
                      : 'Export fehlgeschlagen'}
                  </p>
                  {lastResult.success && (
                    <div className="mt-1 text-xs text-muted-foreground space-y-1">
                      <p>
                        {lastResult.stats.totalSamples} Samples ({lastResult.stats.trainSamples} Train / {lastResult.stats.valSamples} Val / {lastResult.stats.testSamples} Test)
                      </p>
                      <p>
                        {lastResult.stats.samplesWithUmlauts} mit Umlauten | {formatBytes(lastResult.stats.outputSizeBytes)}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Export List */}
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium">Vorhandene Exports</h3>
              <Badge variant="secondary">{exports?.length || 0}</Badge>
            </div>

            {exportsLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-16 bg-muted animate-pulse rounded-lg"
                  />
                ))}
              </div>
            ) : exports?.length === 0 ? (
              <div className="text-center py-8">
                <FolderOpen className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <p className="text-sm text-muted-foreground">
                  Noch keine Exports vorhanden.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {exports?.map((exp) => {
                  const formatInfo = EXPORT_FORMATS.find(
                    (f) => f.value === exp.format
                  );
                  const FormatIcon = formatInfo?.icon || FileJson;

                  return (
                    <div
                      key={exp.exportId}
                      className="flex items-center gap-3 p-3 border rounded-lg"
                    >
                      <div className="h-10 w-10 rounded bg-muted flex items-center justify-center">
                        <FormatIcon className="h-5 w-5 text-muted-foreground" />
                      </div>

                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">
                          {formatInfo?.label || exp.format}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {exp.totalSamples} Samples | {formatDate(exp.createdAt)}
                        </p>
                      </div>

                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Export loeschen?</AlertDialogTitle>
                            <AlertDialogDescription>
                              Der Export wird unwiderruflich geloescht.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={() => handleDelete(exp.exportId)}
                            >
                              Loeschen
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
