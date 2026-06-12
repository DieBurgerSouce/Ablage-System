/**
 * A/B Test Card Component
 *
 * Zeigt aktive A/B Tests und deren Status.
 * Enterprise-Grade mit Error Handling und Feedback.
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FlaskConical, Play, CheckCircle, XCircle, AlertTriangle, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import type { LearningStats } from '../api/ocr-learning-api';
import { useStartABTest, useEndABTest, useABTestResult } from '../hooks/use-ocr-learning';

interface ABTestCardProps {
  stats: LearningStats;
}

export function ABTestCard({ stats }: ABTestCardProps) {
  const [showStartDialog, setShowStartDialog] = useState(false);
  const [showEndDialog, setShowEndDialog] = useState(false);
  const [selectedTestId, setSelectedTestId] = useState<string | null>(null);
  const [newTestConfig, setNewTestConfig] = useState({
    test_id: '',
    candidate_version: 'candidate_a' as 'candidate_a' | 'candidate_b',
    traffic_split: 0.1,
    min_samples: 100,
    max_duration_days: 7,
  });

  const startABTest = useStartABTest();
  const endABTest = useEndABTest();
  const { data: testResult } = useABTestResult(selectedTestId || undefined);

  const activeTests = stats.active_ab_tests || [];

  const handleStartTest = async () => {
    try {
      await startABTest.mutateAsync(newTestConfig);
      setShowStartDialog(false);
      setNewTestConfig({
        test_id: '',
        candidate_version: 'candidate_a',
        traffic_split: 0.1,
        min_samples: 100,
        max_duration_days: 7,
      });
      toast.success('A/B Test erfolgreich gestartet', {
        description: `Test "${newTestConfig.test_id}" läuft jetzt.`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast.error('Fehler beim Starten des Tests', {
        description: message,
      });
    }
  };

  const handleEndTest = async (action: 'promote' | 'rollback') => {
    if (selectedTestId) {
      try {
        await endABTest.mutateAsync({ testId: selectedTestId, action });
        setShowEndDialog(false);
        const actionText = action === 'promote' ? 'befördert' : 'zurückgerollt';
        toast.success(`Test erfolgreich ${actionText}`, {
          description: `Test "${selectedTestId}" wurde ${actionText}.`,
        });
        setSelectedTestId(null);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
        toast.error('Fehler beim Beenden des Tests', {
          description: message,
        });
      }
    }
  };

  const getRecommendationBadge = (recommendation: string) => {
    switch (recommendation) {
      case 'promote':
        return <Badge className="bg-green-500">Befördern</Badge>;
      case 'rollback':
        return <Badge variant="destructive">Zurückrollen</Badge>;
      default:
        return <Badge variant="secondary">Fortsetzen</Badge>;
    }
  };

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <FlaskConical className="w-5 h-5" />
            A/B Tests
          </CardTitle>
          <Button size="sm" onClick={() => setShowStartDialog(true)}>
            <Play className="w-4 h-4 mr-2" />
            Neuer Test
          </Button>
        </CardHeader>
        <CardContent>
          {activeTests.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <FlaskConical className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>Keine aktiven A/B Tests</p>
              <p className="text-sm mt-2">
                Starten Sie einen Test um verschiedene Modell-Versionen zu vergleichen.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {activeTests.map((test) => (
                <div
                  key={test.test_id}
                  className="border rounded-lg p-4 hover:bg-muted/50 cursor-pointer"
                  onClick={() => {
                    setSelectedTestId(test.test_id);
                    setShowEndDialog(true);
                  }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium">{test.test_id}</span>
                    {test.is_expired ? (
                      <Badge variant="outline" className="text-yellow-500 border-yellow-500">
                        <AlertTriangle className="w-3 h-3 mr-1" />
                        Abgelaufen
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-green-500 border-green-500">
                        Aktiv
                      </Badge>
                    )}
                  </div>
                  <div className="text-sm text-muted-foreground mb-2">
                    Kandidat: <span className="font-mono">{test.candidate}</span> |
                    Traffic: {(test.traffic_split * 100).toFixed(0)}%
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Gestartet: {new Date(test.started_at).toLocaleDateString('de-DE')}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Start Test Dialog */}
      <Dialog open={showStartDialog} onOpenChange={setShowStartDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Neuen A/B Test starten</DialogTitle>
            <DialogDescription>
              Vergleichen Sie eine neue Modell-Version mit der aktuellen Baseline.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="test_id">Test-ID</Label>
              <Input
                id="test_id"
                placeholder="z.B. test-2026-01-19"
                value={newTestConfig.test_id}
                onChange={(e) =>
                  setNewTestConfig({ ...newTestConfig, test_id: e.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="candidate">Kandidat-Version</Label>
              <Select
                value={newTestConfig.candidate_version}
                onValueChange={(v) =>
                  setNewTestConfig({
                    ...newTestConfig,
                    candidate_version: v as 'candidate_a' | 'candidate_b',
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="candidate_a">Kandidat A</SelectItem>
                  <SelectItem value="candidate_b">Kandidat B</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="traffic">Traffic-Anteil (%)</Label>
                <Input
                  id="traffic"
                  type="number"
                  min={1}
                  max={50}
                  value={newTestConfig.traffic_split * 100}
                  onChange={(e) =>
                    setNewTestConfig({
                      ...newTestConfig,
                      traffic_split: Number(e.target.value) / 100,
                    })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="samples">Min. Samples</Label>
                <Input
                  id="samples"
                  type="number"
                  min={10}
                  value={newTestConfig.min_samples}
                  onChange={(e) =>
                    setNewTestConfig({
                      ...newTestConfig,
                      min_samples: Number(e.target.value),
                    })
                  }
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="duration">Max. Dauer (Tage)</Label>
              <Input
                id="duration"
                type="number"
                min={1}
                max={30}
                value={newTestConfig.max_duration_days}
                onChange={(e) =>
                  setNewTestConfig({
                    ...newTestConfig,
                    max_duration_days: Number(e.target.value),
                  })
                }
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowStartDialog(false)}>
              Abbrechen
            </Button>
            <Button
              onClick={handleStartTest}
              disabled={!newTestConfig.test_id || startABTest.isPending}
            >
              {startABTest.isPending ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Play className="w-4 h-4 mr-2" />
              )}
              {startABTest.isPending ? 'Starte...' : 'Test starten'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* End Test Dialog */}
      <Dialog open={showEndDialog} onOpenChange={setShowEndDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>A/B Test: {selectedTestId}</DialogTitle>
            <DialogDescription>
              Ergebnis und Aktionen für den laufenden Test.
            </DialogDescription>
          </DialogHeader>
          {testResult && (
            <div className="space-y-4 py-4">
              <div className="flex items-center justify-between">
                <span>Verbesserung:</span>
                <span
                  className={`font-bold ${
                    testResult.improvement_percent > 0
                      ? 'text-green-500'
                      : 'text-red-500'
                  }`}
                >
                  {testResult.improvement_percent > 0 ? '+' : ''}
                  {testResult.improvement_percent.toFixed(1)}%
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Statistisch signifikant:</span>
                {testResult.is_significant ? (
                  <CheckCircle className="w-5 h-5 text-green-500" />
                ) : (
                  <XCircle className="w-5 h-5 text-muted-foreground" />
                )}
              </div>
              <div className="flex items-center justify-between">
                <span>Confidence-Level:</span>
                <span>{(testResult.confidence_level * 100).toFixed(0)}%</span>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Baseline Quality Score</span>
                  <span>{testResult.baseline_quality_score.toFixed(2)}</span>
                </div>
                <Progress value={testResult.baseline_quality_score * 100} className="h-2" />
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Kandidat Quality Score</span>
                  <span>{testResult.candidate_quality_score.toFixed(2)}</span>
                </div>
                <Progress
                  value={testResult.candidate_quality_score * 100}
                  className="h-2"
                />
              </div>
              <div className="flex items-center justify-between pt-2 border-t">
                <span>Empfehlung:</span>
                {getRecommendationBadge(testResult.recommendation)}
              </div>
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setShowEndDialog(false)}>
              Schließen
            </Button>
            <Button
              variant="destructive"
              onClick={() => handleEndTest('rollback')}
              disabled={endABTest.isPending}
            >
              {endABTest.isPending ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <XCircle className="w-4 h-4 mr-2" />
              )}
              Zurückrollen
            </Button>
            <Button
              onClick={() => handleEndTest('promote')}
              disabled={endABTest.isPending}
            >
              {endABTest.isPending ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <CheckCircle className="w-4 h-4 mr-2" />
              )}
              Befördern
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
