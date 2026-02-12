/**
 * AI Settings Panel
 *
 * Konfigurations-Panel für KI-Schwellenwerte.
 */

import { useState } from 'react';
import { Settings, Loader2, TrendingUp } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from '@/components/ui/alert';

import {
  useThresholds,
  useUpdateThreshold,
  useThresholdSuggestions,
  useApplyThresholdSuggestion,
} from '../hooks/useAIAdmin';
import type { ThresholdConfig, DecisionType } from '../types';

// =============================================================================
// Decision Type Labels
// =============================================================================

const DECISION_TYPE_LABELS: Record<DecisionType, { name: string; description: string }> = {
  document_classification: {
    name: 'Dokumenten-Klassifizierung',
    description: 'Automatische Erkennung von Dokumenttypen',
  },
  entity_linking: {
    name: 'Entitäts-Verknüpfung',
    description: 'Zuordnung von Dokumenten zu Kunden/Lieferanten',
  },
  invoice_matching: {
    name: 'Rechnungs-Matching',
    description: 'Zuordnung von Rechnungen zu Bestellungen',
  },
  payment_matching: {
    name: 'Zahlungs-Matching',
    description: 'Zuordnung von Zahlungen zu Rechnungen',
  },
  ocr_correction: {
    name: 'OCR-Korrektur',
    description: 'Automatische Korrektur von OCR-Fehlern',
  },
  anomaly_detection: {
    name: 'Anomalie-Erkennung',
    description: 'Erkennung ungewöhnlicher Transaktionen',
  },
  duplicate_detection: {
    name: 'Duplikat-Erkennung',
    description: 'Erkennung doppelter Dokumente',
  },
  auto_categorization: {
    name: 'Auto-Kategorisierung',
    description: 'Automatische Tag-Vergabe',
  },
};

// =============================================================================
// Threshold Item Component
// =============================================================================

interface ThresholdItemProps {
  threshold: ThresholdConfig;
  onChange: (updates: Partial<ThresholdConfig>) => void;
}

function ThresholdItem({ threshold, onChange }: ThresholdItemProps) {
  const label = DECISION_TYPE_LABELS[threshold.decision_type as DecisionType];

  return (
    <div className="space-y-4 p-4 border rounded-lg">
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <Label className="text-base font-semibold">{label.name}</Label>
          <p className="text-sm text-muted-foreground">{label.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <Switch
            checked={threshold.is_enabled}
            onCheckedChange={(is_enabled) => onChange({ is_enabled })}
          />
          <span className="text-sm">
            {threshold.is_enabled ? 'Aktiv' : 'Inaktiv'}
          </span>
        </div>
      </div>

      <Separator />

      <div className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-sm">Auto-Anwendungs-Schwellenwert</Label>
            <Badge variant="outline">{(threshold.auto_threshold * 100).toFixed(0)}%</Badge>
          </div>
          <Slider
            value={[threshold.auto_threshold]}
            onValueChange={([auto_threshold]) => onChange({ auto_threshold })}
            min={0}
            max={1}
            step={0.05}
            disabled={!threshold.is_enabled}
          />
          <p className="text-xs text-muted-foreground">
            Entscheidungen mit Konfidenz ≥ diesem Wert werden automatisch angewendet
          </p>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-sm">Vorschlags-Schwellenwert</Label>
            <Badge variant="outline">{(threshold.suggest_threshold * 100).toFixed(0)}%</Badge>
          </div>
          <Slider
            value={[threshold.suggest_threshold]}
            onValueChange={([suggest_threshold]) => onChange({ suggest_threshold })}
            min={0}
            max={1}
            step={0.05}
            disabled={!threshold.is_enabled}
          />
          <p className="text-xs text-muted-foreground">
            Entscheidungen mit Konfidenz ≥ diesem Wert werden vorgeschlagen
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Switch
            checked={threshold.allow_auto_apply}
            onCheckedChange={(allow_auto_apply) => onChange({ allow_auto_apply })}
            disabled={!threshold.is_enabled}
          />
          <Label className="text-sm">Automatische Anwendung erlauben</Label>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function AISettingsPanel() {
  const { data: thresholds, isLoading } = useThresholds();
  const { data: suggestions } = useThresholdSuggestions(30);
  const updateThreshold = useUpdateThreshold();
  const applySuggestion = useApplyThresholdSuggestion();

  // Local state for changes
  const [changes, setChanges] = useState<
    Map<DecisionType, Partial<ThresholdConfig>>
  >(new Map());

  const handleChange = (
    decisionType: DecisionType,
    updates: Partial<ThresholdConfig>
  ) => {
    setChanges((prev) => {
      const newMap = new Map(prev);
      const existing = newMap.get(decisionType) || {};
      newMap.set(decisionType, { ...existing, ...updates });
      return newMap;
    });
  };

  const handleSave = async () => {
    for (const [decisionType, updates] of changes.entries()) {
      await updateThreshold.mutateAsync({ decisionType, data: updates });
    }
    setChanges(new Map());
  };

  const handleApplySuggestion = async (decisionType: DecisionType) => {
    await applySuggestion.mutateAsync(decisionType);
  };

  const hasChanges = changes.size > 0;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Merge changes with current thresholds
  const displayThresholds = thresholds?.map((t) => ({
    ...t,
    ...(changes.get(t.decision_type as DecisionType) || {}),
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Settings className="h-5 w-5" />
            KI-Schwellenwerte
          </h3>
          <p className="text-sm text-muted-foreground">
            Konfigurieren Sie die Konfidenz-Schwellenwerte für automatische Entscheidungen
          </p>
        </div>
        {hasChanges && (
          <Button onClick={handleSave} disabled={updateThreshold.isPending}>
            {updateThreshold.isPending && (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            )}
            Änderungen speichern
          </Button>
        )}
      </div>

      {/* Suggestions Alert */}
      {suggestions && suggestions.length > 0 && (
        <Alert>
          <TrendingUp className="h-4 w-4" />
          <AlertTitle>Optimierungs-Vorschläge verfügbar</AlertTitle>
          <AlertDescription>
            Basierend auf den letzten 30 Tagen gibt es {suggestions.length} Vorschläge zur
            Optimierung der Schwellenwerte.
          </AlertDescription>
        </Alert>
      )}

      {/* Suggestions Cards */}
      {suggestions && suggestions.length > 0 && (
        <div className="space-y-3">
          {suggestions.map((suggestion) => {
            const label = DECISION_TYPE_LABELS[suggestion.decision_type];
            return (
              <Card key={suggestion.decision_type}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm">{label.name}</CardTitle>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleApplySuggestion(suggestion.decision_type)}
                      disabled={applySuggestion.isPending}
                    >
                      Vorschlag anwenden
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Aktuell (Auto)</p>
                      <p className="font-semibold">
                        {(suggestion.current_auto * 100).toFixed(0)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Empfohlen (Auto)</p>
                      <p className="font-semibold text-green-600">
                        {(suggestion.suggested_auto * 100).toFixed(0)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Aktuell (Vorschlag)</p>
                      <p className="font-semibold">
                        {(suggestion.current_suggest * 100).toFixed(0)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Empfohlen (Vorschlag)</p>
                      <p className="font-semibold text-green-600">
                        {(suggestion.suggested_suggest * 100).toFixed(0)}%
                      </p>
                    </div>
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground">{suggestion.reason}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Threshold Items */}
      <div className="space-y-4">
        {displayThresholds?.map((threshold) => (
          <ThresholdItem
            key={threshold.decision_type}
            threshold={threshold}
            onChange={(updates) =>
              handleChange(threshold.decision_type as DecisionType, updates)
            }
          />
        ))}
      </div>
    </div>
  );
}
