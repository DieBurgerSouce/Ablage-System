/**
 * A/B Test Comparison Component
 *
 * Vision 2.0 Phase 3: MLOps Dashboard Enhancement
 * Vergleicht zwei Modellversionen in einem A/B Test.
 */

import { useState } from 'react';
import {
  FlaskConical,
  Play,
  Square,
  Trophy,
  TrendingUp,
  TrendingDown,
  Loader2,
  Plus,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { toast } from 'sonner';
import {
  useABTests,
  useStartABTest,
  useEndABTest,
  useModelVersions,
  type ABTest,
  type ABTestStatus,
  type ModelType,
} from '../hooks/useMLOps';

const MODEL_TYPE_LABELS: Record<ModelType, string> = {
  ocr_confidence: 'OCR Confidence',
  ocr_backend_router: 'Backend Router',
  document_classifier: 'Dokumentenklassifikation',
  entity_matcher: 'Entity Matching',
  extraction_model: 'Feldextraktion',
};

const STATUS_CONFIG: Record<ABTestStatus, { label: string; color: string }> = {
  running: { label: 'Laeuft', color: 'bg-blue-100 text-blue-800' },
  completed: { label: 'Abgeschlossen', color: 'bg-green-100 text-green-800' },
  cancelled: { label: 'Abgebrochen', color: 'bg-gray-100 text-gray-800' },
};

function TestRow({
  test,
  onEnd,
  isEnding,
}: {
  test: ABTest;
  onEnd: () => void;
  isEnding: boolean;
}) {
  const statusConfig = STATUS_CONFIG[test.status];
  const hasWinner = test.winner !== null;
  const isRunning = test.status === 'running';

  const getAccuracyDiff = () => {
    if (test.accuracy_a === null || test.accuracy_b === null) return null;
    return test.accuracy_b - test.accuracy_a;
  };

  const accuracyDiff = getAccuracyDiff();

  return (
    <TableRow>
      <TableCell>
        <div>
          <div className="font-medium">{test.name}</div>
          <div className="text-xs text-muted-foreground">
            {MODEL_TYPE_LABELS[test.model_type]}
          </div>
        </div>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Badge variant={test.winner === 'a' ? 'default' : 'outline'}>
            A: {test.variant_a_version}
          </Badge>
          <span className="text-muted-foreground">vs</span>
          <Badge variant={test.winner === 'b' ? 'default' : 'outline'}>
            B: {test.variant_b_version}
          </Badge>
        </div>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <div className="w-24">
            <Progress value={test.traffic_split} className="h-2" />
          </div>
          <span className="text-sm text-muted-foreground">
            {100 - test.traffic_split}% / {test.traffic_split}%
          </span>
        </div>
      </TableCell>
      <TableCell>
        <div className="text-sm">
          <div>A: {test.samples_a.toLocaleString('de-DE')}</div>
          <div>B: {test.samples_b.toLocaleString('de-DE')}</div>
        </div>
      </TableCell>
      <TableCell>
        <div className="text-sm">
          {test.accuracy_a !== null && test.accuracy_b !== null ? (
            <div className="flex items-center gap-2">
              <div>
                A: {(test.accuracy_a * 100).toFixed(1)}%
                <br />
                B: {(test.accuracy_b * 100).toFixed(1)}%
              </div>
              {accuracyDiff !== null && (
                <div className="flex items-center">
                  {accuracyDiff > 0 ? (
                    <TrendingUp className="h-4 w-4 text-green-500" />
                  ) : accuracyDiff < 0 ? (
                    <TrendingDown className="h-4 w-4 text-red-500" />
                  ) : null}
                  <span
                    className={`text-xs ${
                      accuracyDiff > 0
                        ? 'text-green-500'
                        : accuracyDiff < 0
                        ? 'text-red-500'
                        : ''
                    }`}
                  >
                    {accuracyDiff > 0 ? '+' : ''}
                    {(accuracyDiff * 100).toFixed(2)}%
                  </span>
                </div>
              )}
            </div>
          ) : (
            <span className="text-muted-foreground">Noch keine Daten</span>
          )}
        </div>
      </TableCell>
      <TableCell>
        <Badge className={statusConfig.color}>
          {statusConfig.label}
        </Badge>
        {hasWinner && (
          <div className="flex items-center gap-1 mt-1 text-xs">
            <Trophy className="h-3 w-3 text-yellow-500" />
            Variante {test.winner?.toUpperCase()} gewinnt
            {test.is_significant && (
              <Badge variant="outline" className="text-xs ml-1">
                p {'<'} 0.05
              </Badge>
            )}
          </div>
        )}
      </TableCell>
      <TableCell>
        {isRunning && (
          <Button
            size="sm"
            variant="outline"
            onClick={onEnd}
            disabled={isEnding}
          >
            {isEnding ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Square className="h-4 w-4" />
            )}
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

function NewABTestDialog() {
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState('');
  const [modelType, setModelType] = useState<ModelType>('ocr_confidence');
  const [variantA, setVariantA] = useState('');
  const [variantB, setVariantB] = useState('');
  const [trafficSplit, setTrafficSplit] = useState(50);

  const startMutation = useStartABTest();
  const { data: versions, isLoading: versionsLoading } = useModelVersions(modelType);

  const handleSubmit = async () => {
    if (!name || !variantA || !variantB) {
      toast.error('Bitte fuellen Sie alle Felder aus');
      return;
    }

    try {
      await startMutation.mutateAsync({
        name,
        modelType,
        variantAVersion: variantA,
        variantBVersion: variantB,
        trafficSplit,
      });
      toast.success('A/B Test wurde gestartet');
      setIsOpen(false);
      // Reset form
      setName('');
      setVariantA('');
      setVariantB('');
      setTrafficSplit(50);
    } catch {
      toast.error('Fehler beim Starten des A/B Tests');
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="h-4 w-4 mr-2" />
          Neuer A/B Test
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Neuen A/B Test starten</DialogTitle>
          <DialogDescription>
            Vergleichen Sie zwei Modellversionen um die beste zu finden.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="name">Testname</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. OCR Confidence v2 vs v3"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="modelType">Modelltyp</Label>
            <Select
              value={modelType}
              onValueChange={(v) => {
                setModelType(v as ModelType);
                setVariantA('');
                setVariantB('');
              }}
            >
              <SelectTrigger>
                <SelectValue />
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
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="variantA">Variante A (Kontrolle)</Label>
              <Select
                value={variantA}
                onValueChange={setVariantA}
                disabled={versionsLoading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Version waehlen" />
                </SelectTrigger>
                <SelectContent>
                  {versions?.map((v) => (
                    <SelectItem key={v.version} value={v.version}>
                      {v.version} ({v.status})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="variantB">Variante B (Test)</Label>
              <Select
                value={variantB}
                onValueChange={setVariantB}
                disabled={versionsLoading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Version waehlen" />
                </SelectTrigger>
                <SelectContent>
                  {versions
                    ?.filter((v) => v.version !== variantA)
                    .map((v) => (
                      <SelectItem key={v.version} value={v.version}>
                        {v.version} ({v.status})
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label>Traffic-Split (% fuer Variante B)</Label>
            <div className="flex items-center gap-4">
              <Slider
                value={[trafficSplit]}
                onValueChange={(v) => setTrafficSplit(v[0])}
                max={100}
                step={5}
                className="flex-1"
              />
              <span className="w-12 text-right font-medium">{trafficSplit}%</span>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)}>
            Abbrechen
          </Button>
          <Button onClick={handleSubmit} disabled={startMutation.isPending}>
            {startMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            Test starten
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ABTestComparison() {
  const { data: tests, isLoading, refetch } = useABTests(undefined, undefined, 10);
  const endMutation = useEndABTest();
  const [endingId, setEndingId] = useState<string | null>(null);

  const handleEndTest = async (testId: string) => {
    setEndingId(testId);
    try {
      await endMutation.mutateAsync({ testId });
      toast.success('A/B Test wurde beendet');
    } catch {
      toast.error('Fehler beim Beenden des Tests');
    } finally {
      setEndingId(null);
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64 mt-1" />
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const runningTests = tests?.filter((t) => t.status === 'running') || [];
  const completedTests = tests?.filter((t) => t.status !== 'running') || [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5" />
            A/B Tests
          </CardTitle>
          <CardDescription>
            Vergleichen Sie Modellversionen mit statistischer Signifikanz
          </CardDescription>
        </div>
        <NewABTestDialog />
      </CardHeader>
      <CardContent>
        {runningTests.length > 0 && (
          <div className="mb-4 p-4 bg-blue-500/10 border border-blue-500/20 rounded-lg">
            <div className="flex items-center gap-2 text-blue-500">
              <Play className="h-4 w-4" />
              <span className="font-medium">
                {runningTests.length} Test{runningTests.length > 1 ? 's' : ''} aktiv
              </span>
            </div>
          </div>
        )}

        {tests && tests.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Varianten</TableHead>
                <TableHead>Traffic</TableHead>
                <TableHead>Samples</TableHead>
                <TableHead>Accuracy</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {tests.map((test) => (
                <TestRow
                  key={test.id}
                  test={test}
                  onEnd={() => handleEndTest(test.id)}
                  isEnding={endingId === test.id}
                />
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <FlaskConical className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>Noch keine A/B Tests durchgefuehrt</p>
            <p className="text-sm mt-1">
              Starten Sie einen Test um Modellversionen zu vergleichen
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
