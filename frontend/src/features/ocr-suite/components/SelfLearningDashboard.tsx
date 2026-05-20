import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useSelfLearningStats } from '../hooks/use-ocr-suite-queries';
import { Brain, TrendingUp, FileText, Cpu, Calendar } from 'lucide-react';

export function SelfLearningDashboard() {
  const { data: stats, isLoading } = useSelfLearningStats();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Self-Learning Dashboard</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Lade Statistiken...</p>
        </CardContent>
      </Card>
    );
  }

  if (!stats) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Self-Learning Dashboard</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Keine Statistiken verfügbar.</p>
        </CardContent>
      </Card>
    );
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Noch nie';
    return new Date(dateString).toLocaleString('de-DE');
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="w-5 h-5" />
            Self-Learning Dashboard
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Übersicht über das selbstlernende OCR-System
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Korrekturen gesamt</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalCorrections}</div>
            <p className="text-xs text-muted-foreground">
              Von Benutzern eingereichte Korrekturen
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Genauigkeitsverbesserung</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {(stats.accuracyImprovement * 100).toFixed(1)}%
            </div>
            <p className="text-xs text-muted-foreground">
              Steigerung der OCR-Genauigkeit
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Verarbeitete Dokumente</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.documentsProcessed}</div>
            <p className="text-xs text-muted-foreground">
              Dokumente mit OCR verarbeitet
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Aktive Modelle</CardTitle>
            <Cpu className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.activeModels}</div>
            <p className="text-xs text-muted-foreground">
              Trainierte OCR-Modelle im Einsatz
            </p>
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Letztes Training</CardTitle>
            <Calendar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatDate(stats.lastTraining)}</div>
            <p className="text-xs text-muted-foreground">
              Zeitpunkt des letzten Modell-Trainings
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Über Self-Learning</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p>
            Das Self-Learning-System nutzt Ihre Korrekturen, um die OCR-Genauigkeit kontinuierlich
            zu verbessern. Jedes Feedback wird analysiert und fließt in das Training neuer Modelle ein.
          </p>
          <p>
            Je mehr Korrekturen eingereicht werden, desto besser wird das System bei der Erkennung
            Ihrer spezifischen Dokumente.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
