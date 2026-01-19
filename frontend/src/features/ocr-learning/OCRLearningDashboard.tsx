/**
 * OCR Self-Learning Dashboard
 *
 * Hauptansicht fuer das selbstlernende OCR-System.
 * Zeigt Lernstatistiken, Confidence-Anpassungen, A/B Tests und Modell-Metriken.
 */

import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Brain, BarChart3, FlaskConical, Settings, AlertTriangle } from 'lucide-react';
import { useLearningStats } from './hooks/use-ocr-learning';
import {
  LearningStatsCards,
  ConfidenceAdjustmentsChart,
  ABTestCard,
  FieldAdjustmentsTable,
  LearningModeSelector,
  ModelMetricsCard,
} from './components';

export function OCRLearningDashboard() {
  const { data: stats, isLoading, error } = useLearningStats();

  if (isLoading) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center gap-3">
          <Brain className="w-8 h-8" />
          <div>
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-4 w-96 mt-2" />
          </div>
        </div>
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <div className="grid grid-cols-2 gap-6">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="p-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Fehler beim Laden</AlertTitle>
          <AlertDescription>
            Die Learning-Statistiken konnten nicht geladen werden.
            {error instanceof Error && <span className="block mt-1">{error.message}</span>}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-3 rounded-lg bg-primary/10">
          <Brain className="w-8 h-8 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">OCR Self-Learning</h1>
          <p className="text-muted-foreground">
            Automatisches Lernen aus User-Korrekturen fuer kontinuierliche Verbesserung.
          </p>
        </div>
      </div>

      {/* Stats Overview */}
      <LearningStatsCards stats={stats} />

      {/* Tabs */}
      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4" />
            Uebersicht
          </TabsTrigger>
          <TabsTrigger value="ab-tests" className="flex items-center gap-2">
            <FlaskConical className="w-4 h-4" />
            A/B Tests
          </TabsTrigger>
          <TabsTrigger value="settings" className="flex items-center gap-2">
            <Settings className="w-4 h-4" />
            Einstellungen
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ConfidenceAdjustmentsChart stats={stats} />
            <ModelMetricsCard stats={stats} />
          </div>
          <FieldAdjustmentsTable stats={stats} />
        </TabsContent>

        {/* A/B Tests Tab */}
        <TabsContent value="ab-tests" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ABTestCard stats={stats} />
            <Card>
              <CardContent className="pt-6">
                <h3 className="font-medium mb-4">A/B Test Anleitung</h3>
                <div className="space-y-3 text-sm text-muted-foreground">
                  <p>
                    Mit A/B Tests koennen Sie neue Modell-Versionen gegen die aktuelle
                    Baseline testen, bevor Sie sie produktiv einsetzen.
                  </p>
                  <div className="space-y-2">
                    <p className="font-medium text-foreground">So funktioniert es:</p>
                    <ol className="list-decimal list-inside space-y-1">
                      <li>Starten Sie einen Test mit gewuenschtem Traffic-Anteil</li>
                      <li>Der Kandidat erhaelt den definierten Anteil der Dokumente</li>
                      <li>Nach genuegend Samples wird die Qualitaet verglichen</li>
                      <li>Bei Verbesserung: Kandidat zur neuen Baseline befoerdern</li>
                      <li>Bei Verschlechterung: Automatisches Rollback</li>
                    </ol>
                  </div>
                  <Alert>
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription>
                      Es kann nur ein A/B Test gleichzeitig laufen. Beenden Sie den
                      aktuellen Test bevor Sie einen neuen starten.
                    </AlertDescription>
                  </Alert>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Settings Tab */}
        <TabsContent value="settings" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <LearningModeSelector stats={stats} />
            <Card>
              <CardContent className="pt-6">
                <h3 className="font-medium mb-4">Lernmodus-Erklaerung</h3>
                <div className="space-y-4 text-sm text-muted-foreground">
                  <div>
                    <p className="font-medium text-foreground">Aggressiv</p>
                    <p>
                      Jede User-Korrektur wird sofort in das System uebernommen. Dies
                      fuehrt zu schnellem Lernen, kann aber bei fehlerhaften Korrekturen
                      zu Problemen fuehren.
                    </p>
                  </div>
                  <div>
                    <p className="font-medium text-foreground">Vorsichtig</p>
                    <p>
                      Nur Korrekturen von verifizierten Benutzern werden uebernommen.
                      Zusaetzlich wird eine Mindest-Confidence benoetigt.
                    </p>
                  </div>
                  <div>
                    <p className="font-medium text-foreground">Batch</p>
                    <p>
                      Korrekturen werden gesammelt und taeglich im Batch verarbeitet.
                      Dies erlaubt eine manuelle Pruefung vor der Uebernahme.
                    </p>
                  </div>
                  <Alert>
                    <Brain className="h-4 w-4" />
                    <AlertDescription>
                      Bei {stats.training_samples} Training Samples wird der aggressive
                      Modus empfohlen, da genuegend Daten fuer stabiles Lernen
                      vorhanden sind.
                    </AlertDescription>
                  </Alert>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
