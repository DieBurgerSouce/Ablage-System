/**
 * Streckengeschäft Warnungen Route
 * Warnungen und Hinweise zu Streckengeschäft-Klassifikationen.
 */

import { useState } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { AlertTriangle, AlertCircle, Info, Clock, CheckCircle, XCircle, FileWarning, Shield } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';

type WarningSeverity = 'kritisch' | 'warnung' | 'hinweis';
type WarningType = 'fehlender_beleg' | 'ungueltige_ustid' | 'zm_frist' | 'konflikt' | 'pruefung_faellig';

interface Warning {
  id: string;
  type: WarningType;
  severity: WarningSeverity;
  title: string;
  description: string;
  documentRef?: string;
  deadline?: string;
  resolved: boolean;
}

const mockWarnings: Warning[] = [
  {
    id: '1',
    type: 'fehlender_beleg',
    severity: 'kritisch',
    title: 'Fehlende Gelangensbestätigung',
    description: 'Für die Lieferung nach Frankreich (Rechnung FR-2024-0891) fehlt die Gelangensbestätigung gemäß §17a UStDV.',
    documentRef: 'Rechnung_FR_2024_0891.pdf',
    deadline: '2024-03-01',
    resolved: false,
  },
  {
    id: '2',
    type: 'ungueltige_ustid',
    severity: 'kritisch',
    title: 'Ungültige USt-IdNr. erkannt',
    description: 'Die USt-IdNr. "ATU12345678" des Empfängers konnte nicht über VIES validiert werden.',
    documentRef: 'Lieferschein_AT_2024_0192.pdf',
    resolved: false,
  },
  {
    id: '3',
    type: 'zm_frist',
    severity: 'warnung',
    title: 'ZM-Meldung fällig in 5 Tagen',
    description: 'Die zusammenfassende Meldung für Januar 2024 muss bis zum 25.02.2024 eingereicht werden.',
    deadline: '2024-02-25',
    resolved: false,
  },
  {
    id: '4',
    type: 'konflikt',
    severity: 'warnung',
    title: 'Widersprüchliche Lieferantenangaben',
    description: 'Das Dokument enthält widersprüchliche Angaben zur Lieferadresse. Bitte manuelle Prüfung durchführen.',
    documentRef: 'Rechnung_NL_2024_0234.pdf',
    resolved: false,
  },
  {
    id: '5',
    type: 'pruefung_faellig',
    severity: 'hinweis',
    title: 'Manuelle Prüfung empfohlen',
    description: 'Klassifikation mit mittlerer Konfidenz (65%) sollte manuell geprüft werden.',
    documentRef: 'Lieferschein_BE_2024_0567.pdf',
    resolved: false,
  },
  {
    id: '6',
    type: 'fehlender_beleg',
    severity: 'warnung',
    title: 'CMR-Frachtbrief fehlt',
    description: 'Für die grenzüberschreitende Lieferung nach Polen fehlt der CMR-Frachtbrief als Nachweis.',
    documentRef: 'Rechnung_PL_2024_0445.pdf',
    deadline: '2024-02-28',
    resolved: false,
  },
  {
    id: '7',
    type: 'zm_frist',
    severity: 'hinweis',
    title: 'ZM-Vorschau verfügbar',
    description: 'Die Vorschau für die ZM Februar 2024 steht zur Kontrolle bereit.',
    resolved: false,
  },
  {
    id: '8',
    type: 'ungueltige_ustid',
    severity: 'kritisch',
    title: 'USt-IdNr. Format ungültig',
    description: 'Die angegebene USt-IdNr. "INVALID123" entspricht nicht dem EU-Format.',
    documentRef: 'Rechnung_ES_2024_0789.pdf',
    resolved: false,
  },
];

const severityConfig: Record<WarningSeverity, {
  icon: React.ElementType;
  color: string;
  bgColor: string;
  borderColor: string;
}> = {
  kritisch: {
    icon: AlertCircle,
    color: 'text-red-600',
    bgColor: 'bg-red-50 dark:bg-red-950',
    borderColor: 'border-l-red-500',
  },
  warnung: {
    icon: AlertTriangle,
    color: 'text-amber-600',
    bgColor: 'bg-amber-50 dark:bg-amber-950',
    borderColor: 'border-l-amber-500',
  },
  hinweis: {
    icon: Info,
    color: 'text-blue-600',
    bgColor: 'bg-blue-50 dark:bg-blue-950',
    borderColor: 'border-l-blue-500',
  },
};

const typeLabels: Record<WarningType, string> = {
  fehlender_beleg: 'Fehlender Beleg',
  ungueltige_ustid: 'USt-IdNr.',
  zm_frist: 'ZM-Frist',
  konflikt: 'Konflikt',
  pruefung_faellig: 'Prüfung fällig',
};

function WarningsPage() {
  const { toast } = useToast();
  const [warnings, setWarnings] = useState<Warning[]>(mockWarnings);
  const [showResolved, setShowResolved] = useState(false);

  const handleResolve = (id: string) => {
    setWarnings((prev) =>
      prev.map((warning) =>
        warning.id === id ? { ...warning, resolved: true } : warning
      )
    );
    toast({
      title: 'Warnung behoben',
      description: 'Die Warnung wurde als behoben markiert.',
    });
  };

  const handleDismiss = (id: string) => {
    setWarnings((prev) => prev.filter((warning) => warning.id !== id));
    toast({
      title: 'Warnung verworfen',
      description: 'Die Warnung wurde aus der Liste entfernt.',
      variant: 'destructive',
    });
  };

  const displayedWarnings = showResolved
    ? warnings
    : warnings.filter((w) => !w.resolved);

  const sortedWarnings = [...displayedWarnings].sort((a, b) => {
    const severityOrder = { kritisch: 0, warnung: 1, hinweis: 2 };
    return severityOrder[a.severity] - severityOrder[b.severity];
  });

  const stats = {
    kritisch: warnings.filter((w) => w.severity === 'kritisch' && !w.resolved).length,
    warnung: warnings.filter((w) => w.severity === 'warnung' && !w.resolved).length,
    hinweis: warnings.filter((w) => w.severity === 'hinweis' && !w.resolved).length,
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight font-display flex items-center gap-2">
            <FileWarning className="h-6 w-6" />
            Warnungen
          </h1>
          <p className="text-muted-foreground mt-1">
            Warnungen und Hinweise zu Streckengeschäft-Klassifikationen
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id="show-resolved"
            checked={showResolved}
            onCheckedChange={setShowResolved}
          />
          <Label htmlFor="show-resolved" className="cursor-pointer">
            Erledigte anzeigen
          </Label>
        </div>
      </div>

      {/* Summary Bar */}
      <Card>
        <CardContent className="pt-6">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-full bg-red-100 dark:bg-red-950 flex items-center justify-center">
                <AlertCircle className="h-6 w-6 text-red-600" />
              </div>
              <div>
                <div className="text-2xl font-bold">{stats.kritisch}</div>
                <div className="text-sm text-muted-foreground">Kritische Warnungen</div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-full bg-amber-100 dark:bg-amber-950 flex items-center justify-center">
                <AlertTriangle className="h-6 w-6 text-amber-600" />
              </div>
              <div>
                <div className="text-2xl font-bold">{stats.warnung}</div>
                <div className="text-sm text-muted-foreground">Warnungen</div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-full bg-blue-100 dark:bg-blue-950 flex items-center justify-center">
                <Info className="h-6 w-6 text-blue-600" />
              </div>
              <div>
                <div className="text-2xl font-bold">{stats.hinweis}</div>
                <div className="text-sm text-muted-foreground">Hinweise</div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Warnings List */}
      <div className="space-y-3">
        {sortedWarnings.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <CheckCircle className="h-12 w-12 mx-auto text-green-500 mb-3" />
              <h3 className="text-lg font-semibold mb-1">Keine offenen Warnungen</h3>
              <p className="text-muted-foreground">
                Alle Warnungen wurden behoben oder es gibt aktuell keine Probleme.
              </p>
            </CardContent>
          </Card>
        ) : (
          sortedWarnings.map((warning) => {
            const config = severityConfig[warning.severity];
            const Icon = config.icon;

            return (
              <Card
                key={warning.id}
                className={cn(
                  'border-l-4 transition-opacity',
                  config.borderColor,
                  config.bgColor,
                  warning.resolved && 'opacity-50'
                )}
              >
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3 flex-1">
                      <Icon className={cn('h-5 w-5 mt-0.5', config.color)} />
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <CardTitle className="text-base">{warning.title}</CardTitle>
                          <Badge variant="outline" className="text-xs">
                            {typeLabels[warning.type]}
                          </Badge>
                          {warning.resolved && (
                            <Badge variant="default" className="bg-green-500 text-xs">
                              <CheckCircle className="h-3 w-3 mr-1" />
                              Behoben
                            </Badge>
                          )}
                        </div>
                        <CardDescription>{warning.description}</CardDescription>
                      </div>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between">
                    <div className="space-y-1 text-sm text-muted-foreground">
                      {warning.documentRef && (
                        <div className="flex items-center gap-1">
                          <FileWarning className="h-4 w-4" />
                          <span className="font-mono">{warning.documentRef}</span>
                        </div>
                      )}
                      {warning.deadline && (
                        <div className="flex items-center gap-1">
                          <Clock className="h-4 w-4" />
                          <span>Frist: {new Date(warning.deadline).toLocaleDateString('de-DE')}</span>
                        </div>
                      )}
                    </div>

                    {!warning.resolved && (
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleResolve(warning.id)}
                        >
                          <CheckCircle className="h-4 w-4 mr-1" />
                          Beheben
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDismiss(warning.id)}
                        >
                          <XCircle className="h-4 w-4 mr-1" />
                          Verwerfen
                        </Button>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}

export const Route = createFileRoute('/streckengeschaeft/warnungen')({
  component: WarningsPage,
});
