/**
 * Model Registry Table
 *
 * Zeigt alle registrierten Modelle mit Versionen und Status.
 */

import { useState } from 'react';
import {
  Brain,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  Clock,
  AlertTriangle,
  Archive,
  RotateCcw,
  ArrowUp,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
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
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import {
  useModelVersions,
  useActiveModel,
  usePromoteModel,
  useRollbackModel,
  type ModelType,
  type ModelStatus,
  type ModelVersion,
} from '../hooks/useMLOps';

// Model Types mit deutschen Labels
const MODEL_TYPES: Array<{ type: ModelType; label: string; description: string }> = [
  {
    type: 'ocr_confidence',
    label: 'OCR Confidence',
    description: 'Kalibrierung der OCR-Konfidenzwerte',
  },
  {
    type: 'ocr_backend_router',
    label: 'Backend Router',
    description: 'Intelligente Backend-Auswahl',
  },
  {
    type: 'document_classifier',
    label: 'Dokumentenklassifikation',
    description: 'Automatische Dokumenttyp-Erkennung',
  },
  {
    type: 'entity_matcher',
    label: 'Entity Matching',
    description: 'Zuordnung zu Geschäftspartnern',
  },
  {
    type: 'extraction_model',
    label: 'Feldextraktion',
    description: 'Extraktion von Rechnungsdaten',
  },
];

const STATUS_CONFIG: Record<
  ModelStatus,
  { label: string; icon: typeof CheckCircle; variant: 'default' | 'secondary' | 'destructive' | 'outline' }
> = {
  draft: { label: 'Entwurf', icon: Clock, variant: 'secondary' },
  candidate: { label: 'Kandidat', icon: Clock, variant: 'outline' },
  active: { label: 'Aktiv', icon: CheckCircle, variant: 'default' },
  deprecated: { label: 'Veraltet', icon: Archive, variant: 'secondary' },
  rolled_back: { label: 'Zurückgesetzt', icon: RotateCcw, variant: 'destructive' },
  archived: { label: 'Archiviert', icon: Archive, variant: 'secondary' },
};

interface ModelTypeRowProps {
  modelType: ModelType;
  label: string;
  description: string;
}

function ModelTypeRow({ modelType, label, description }: ModelTypeRowProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { data: versions, isLoading: versionsLoading } = useModelVersions(modelType);
  const { data: activeModel, isLoading: activeLoading } = useActiveModel(modelType);
  const promoteMutation = usePromoteModel();
  const rollbackMutation = useRollbackModel();
  const [rollbackReason, setRollbackReason] = useState('');

  const handlePromote = async (version: string) => {
    try {
      await promoteMutation.mutateAsync({ modelType, version });
      toast.success(`Modell v${version} wurde aktiviert`);
    } catch {
      toast.error('Fehler beim Aktivieren des Modells');
    }
  };

  const handleRollback = async () => {
    if (!rollbackReason.trim()) {
      toast.error('Bitte geben Sie einen Grund an');
      return;
    }
    try {
      const result = await rollbackMutation.mutateAsync({
        modelType,
        reason: rollbackReason,
      });
      if (result) {
        toast.success(`Rollback zu v${result.version} erfolgreich`);
      } else {
        toast.warning('Kein Rollback-Ziel gefunden');
      }
      setRollbackReason('');
    } catch {
      toast.error('Fehler beim Rollback');
    }
  };

  const isLoading = versionsLoading || activeLoading;

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="border rounded-lg">
      <CollapsibleTrigger asChild>
        <div className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50 transition-colors">
          <div className="flex items-center gap-3">
            {isOpen ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
            <Brain className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="font-medium">{label}</p>
              <p className="text-sm text-muted-foreground">{description}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {isLoading ? (
              <Skeleton className="h-6 w-20" />
            ) : activeModel ? (
              <>
                <Badge variant="default">v{activeModel.version}</Badge>
                {activeModel.accuracy && (
                  <span className="text-sm text-muted-foreground">
                    {(activeModel.accuracy * 100).toFixed(1)}% Accuracy
                  </span>
                )}
              </>
            ) : (
              <Badge variant="secondary">Kein aktives Modell</Badge>
            )}
          </div>
        </div>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="border-t p-4">
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : versions && versions.length > 0 ? (
            <div className="space-y-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Version</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Accuracy</TableHead>
                    <TableHead>Deployed</TableHead>
                    <TableHead className="text-right">Aktionen</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {versions.map((v) => {
                    const statusConfig = STATUS_CONFIG[v.status];
                    const StatusIcon = statusConfig.icon;
                    return (
                      <TableRow key={v.version}>
                        <TableCell className="font-mono">v{v.version}</TableCell>
                        <TableCell>
                          <Badge variant={statusConfig.variant} className="gap-1">
                            <StatusIcon className="h-3 w-3" />
                            {statusConfig.label}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {v.accuracy ? `${(v.accuracy * 100).toFixed(1)}%` : '-'}
                        </TableCell>
                        <TableCell>
                          {v.deployed_at
                            ? new Date(v.deployed_at).toLocaleDateString('de-DE')
                            : '-'}
                        </TableCell>
                        <TableCell className="text-right">
                          {v.status !== 'active' && v.status !== 'archived' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handlePromote(v.version)}
                              disabled={promoteMutation.isPending}
                            >
                              <ArrowUp className="h-4 w-4 mr-1" />
                              Aktivieren
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>

              {activeModel && (
                <div className="flex justify-end">
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="outline" size="sm">
                        <RotateCcw className="h-4 w-4 mr-2" />
                        Rollback
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Modell zurücksetzen?</AlertDialogTitle>
                        <AlertDialogDescription>
                          Das aktive Modell v{activeModel.version} wird deaktiviert und
                          die vorherige Version wird wiederhergestellt.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <div className="py-4">
                        <Label htmlFor="reason">Grund für Rollback</Label>
                        <Input
                          id="reason"
                          value={rollbackReason}
                          onChange={(e) => setRollbackReason(e.target.value)}
                          placeholder="z.B. Accuracy-Verschlechterung, Fehler in Produktion"
                          className="mt-2"
                        />
                      </div>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={handleRollback}
                          disabled={rollbackMutation.isPending || !rollbackReason.trim()}
                        >
                          Rollback durchführen
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              )}
            </div>
          ) : (
            <p className="text-center text-muted-foreground py-4">
              Keine Modellversionen registriert
            </p>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ModelRegistryTable() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5" />
          Model Registry
        </CardTitle>
        <CardDescription>
          Alle registrierten Modelle und deren Versionen verwalten
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {MODEL_TYPES.map((mt) => (
          <ModelTypeRow
            key={mt.type}
            modelType={mt.type}
            label={mt.label}
            description={mt.description}
          />
        ))}
      </CardContent>
    </Card>
  );
}
