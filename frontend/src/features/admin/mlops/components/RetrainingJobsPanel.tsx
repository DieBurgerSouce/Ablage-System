/**
 * Retraining Jobs Panel
 *
 * Zeigt laufende und vergangene Retraining Jobs.
 */

import { useState } from 'react';
import {
  RefreshCw,
  Play,
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
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
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  useRetrainingJobs,
  useStartRetraining,
  type ModelType,
  type RetrainingStatus,
  type RetrainingTrigger,
  type RetrainingJob,
} from '../hooks/useMLOps';

const MODEL_TYPE_LABELS: Record<ModelType, string> = {
  ocr_confidence: 'OCR Confidence',
  ocr_backend_router: 'Backend Router',
  document_classifier: 'Dokumentenklassifikation',
  entity_matcher: 'Entity Matching',
  extraction_model: 'Feldextraktion',
};

const STATUS_CONFIG: Record<
  RetrainingStatus,
  { label: string; icon: typeof CheckCircle; color: string }
> = {
  pending: { label: 'Ausstehend', icon: Clock, color: 'text-yellow-500' },
  running: { label: 'Laeuft', icon: Loader2, color: 'text-blue-500' },
  completed: { label: 'Abgeschlossen', icon: CheckCircle, color: 'text-green-500' },
  failed: { label: 'Fehlgeschlagen', icon: XCircle, color: 'text-red-500' },
  cancelled: { label: 'Abgebrochen', icon: XCircle, color: 'text-gray-500' },
};

const TRIGGER_LABELS: Record<RetrainingTrigger, string> = {
  threshold: 'Schwellenwert erreicht',
  scheduled: 'Geplant',
  drift: 'Drift erkannt',
  manual: 'Manuell',
  ab_test_winner: 'A/B Test Gewinner',
};

function formatDuration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt) return '-';

  const start = new Date(startedAt);
  const end = completedAt ? new Date(completedAt) : new Date();
  const durationMs = end.getTime() - start.getTime();

  const minutes = Math.floor(durationMs / 60000);
  const seconds = Math.floor((durationMs % 60000) / 1000);

  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

function JobRow({ job }: { job: RetrainingJob }) {
  const statusConfig = STATUS_CONFIG[job.status];
  const StatusIcon = statusConfig.icon;

  return (
    <TableRow>
      <TableCell>
        <div className="flex items-center gap-2">
          <StatusIcon
            className={`h-4 w-4 ${statusConfig.color} ${
              job.status === 'running' ? 'animate-spin' : ''
            }`}
          />
          <span className={statusConfig.color}>{statusConfig.label}</span>
        </div>
      </TableCell>
      <TableCell>{MODEL_TYPE_LABELS[job.model_type]}</TableCell>
      <TableCell>
        <Badge variant="outline">{TRIGGER_LABELS[job.trigger]}</Badge>
      </TableCell>
      <TableCell>{job.training_samples}</TableCell>
      <TableCell>
        {job.accuracy_before !== null && job.accuracy_after !== null ? (
          <div className="flex items-center gap-1 text-sm">
            <span>{(job.accuracy_before * 100).toFixed(1)}%</span>
            <span className="text-muted-foreground">→</span>
            <span
              className={
                job.accuracy_after > job.accuracy_before
                  ? 'text-green-500'
                  : job.accuracy_after < job.accuracy_before
                  ? 'text-red-500'
                  : ''
              }
            >
              {(job.accuracy_after * 100).toFixed(1)}%
            </span>
          </div>
        ) : (
          '-'
        )}
      </TableCell>
      <TableCell>{formatDuration(job.started_at, job.completed_at)}</TableCell>
      <TableCell className="text-muted-foreground text-sm">
        {new Date(job.created_at).toLocaleString('de-DE', {
          day: '2-digit',
          month: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        })}
      </TableCell>
    </TableRow>
  );
}

export function RetrainingJobsPanel() {
  const { data: jobs, isLoading, refetch } = useRetrainingJobs(20);
  const startRetraining = useStartRetraining();
  const [selectedModelType, setSelectedModelType] = useState<ModelType>('ocr_confidence');
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const handleStartRetraining = async () => {
    try {
      await startRetraining.mutateAsync({
        modelType: selectedModelType,
        trigger: 'manual',
      });
      toast.success('Retraining wurde gestartet');
      setIsDialogOpen(false);
    } catch {
      toast.error('Fehler beim Starten des Retrainings');
    }
  };

  const runningJobs = jobs?.filter((j) => j.status === 'running' || j.status === 'pending') ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Retraining Jobs
          </CardTitle>
          <CardDescription>
            Verlauf und Status der Modell-Retrainings
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Aktualisieren
          </Button>
          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Play className="h-4 w-4 mr-2" />
                Retraining starten
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Manuelles Retraining starten</DialogTitle>
                <DialogDescription>
                  Waehlen Sie den Modelltyp aus, der neu trainiert werden soll.
                  Das Training wird im Hintergrund ausgefuehrt.
                </DialogDescription>
              </DialogHeader>
              <div className="py-4">
                <Select
                  value={selectedModelType}
                  onValueChange={(v) => setSelectedModelType(v as ModelType)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Modelltyp waehlen" />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(MODEL_TYPE_LABELS).map(([type, label]) => (
                      <SelectItem key={type} value={type}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
                  Abbrechen
                </Button>
                <Button onClick={handleStartRetraining} disabled={startRetraining.isPending}>
                  {startRetraining.isPending && (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  )}
                  Starten
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {runningJobs.length > 0 && (
          <div className="mb-4 p-4 bg-blue-500/10 border border-blue-500/20 rounded-lg">
            <div className="flex items-center gap-2 text-blue-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="font-medium">
                {runningJobs.length} Job{runningJobs.length > 1 ? 's' : ''} aktiv
              </span>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : jobs && jobs.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Status</TableHead>
                <TableHead>Modell</TableHead>
                <TableHead>Trigger</TableHead>
                <TableHead>Samples</TableHead>
                <TableHead>Accuracy</TableHead>
                <TableHead>Dauer</TableHead>
                <TableHead>Erstellt</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => (
                <JobRow key={job.id} job={job} />
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <RefreshCw className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>Noch keine Retraining Jobs ausgefuehrt</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
