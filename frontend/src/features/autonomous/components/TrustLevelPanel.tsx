/**
 * Trust Level Panel Component
 * Displays current trust level with visual indicator and allows admin to change level
 */

import { useState } from 'react';
import { Shield, TrendingUp, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { useTrustLevel, useTrustRecommendation, useUpdateTrustLevel } from '../hooks/useAutonomous';
import type { TrustLevelName } from '../types/autonomous-types';

const TRUST_LEVEL_LABELS: Record<TrustLevelName, string> = {
  assistance: 'Assistenzmodus',
  auto_accept: 'Auto-Akzeptanz',
  confidence: 'Konfidenz-basiert',
  autonomous: 'Autonom',
};

const TRUST_LEVEL_COLORS: Record<TrustLevelName, string> = {
  assistance: 'text-blue-600',
  auto_accept: 'text-green-600',
  confidence: 'text-yellow-600',
  autonomous: 'text-purple-600',
};

const TRUST_LEVEL_DESCRIPTIONS: Record<TrustLevelName, string> = {
  assistance: 'KI schlägt vor, Benutzer entscheidet immer',
  auto_accept: 'Hohe Konfidenz wird automatisch akzeptiert',
  confidence: 'Verzögerte Akzeptanz bei mittlerer Konfidenz',
  autonomous: 'Vollständig autonome Entscheidungen',
};

export function TrustLevelPanel() {
  const { data: trustLevel, isLoading } = useTrustLevel();
  const { data: recommendation } = useTrustRecommendation();
  const updateTrustLevel = useUpdateTrustLevel();
  const [selectedLevel, setSelectedLevel] = useState<string>('');

  const handleLevelChange = (value: string) => {
    setSelectedLevel(value);
  };

  const handleApplyLevel = () => {
    if (!selectedLevel) return;

    updateTrustLevel.mutate(
      {
        level: parseInt(selectedLevel, 10),
        reason: 'Manuell durch Admin geändert',
      },
      {
        onSuccess: () => {
          setSelectedLevel('');
        },
      }
    );
  };

  const handleApplyRecommendation = () => {
    if (!recommendation) return;

    updateTrustLevel.mutate({
      level: recommendation.recommended_level,
      reason: `Empfehlung angewendet: ${recommendation.reason}`,
    });
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Vertrauensstufe
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Lädt...</div>
        </CardContent>
      </Card>
    );
  }

  if (!trustLevel) {
    return null;
  }

  const showRecommendation =
    recommendation &&
    recommendation.recommended_level !== recommendation.current_level &&
    recommendation.can_upgrade;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shield className="h-5 w-5" />
          Vertrauensstufe
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Current Level */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shield className={cn('h-6 w-6', TRUST_LEVEL_COLORS[trustLevel.level_name])} />
              <div>
                <div className="font-semibold">
                  Stufe {trustLevel.level}: {TRUST_LEVEL_LABELS[trustLevel.level_name]}
                </div>
                <div className="text-sm text-muted-foreground">
                  {TRUST_LEVEL_DESCRIPTIONS[trustLevel.level_name]}
                </div>
              </div>
            </div>
            <Badge variant={trustLevel.is_enabled ? 'default' : 'secondary'}>
              {trustLevel.is_enabled ? 'Aktiv' : 'Inaktiv'}
            </Badge>
          </div>

          {/* Thresholds */}
          <div className="grid grid-cols-2 gap-4 pt-2">
            <div>
              <div className="text-xs text-muted-foreground mb-1">Sofort-Schwellenwert</div>
              <div className="flex items-center gap-2">
                <Progress value={trustLevel.immediate_threshold * 100} className="flex-1" />
                <span className="text-sm font-medium">
                  {Math.round(trustLevel.immediate_threshold * 100)}%
                </span>
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-1">Verzögerungs-Schwellenwert</div>
              <div className="flex items-center gap-2">
                <Progress value={trustLevel.delayed_threshold * 100} className="flex-1" />
                <span className="text-sm font-medium">
                  {Math.round(trustLevel.delayed_threshold * 100)}%
                </span>
              </div>
            </div>
          </div>

          {/* Delay Hours */}
          {trustLevel.delay_hours > 0 && (
            <div className="text-xs text-muted-foreground">
              Verzögerungszeit: {trustLevel.delay_hours} Stunden
            </div>
          )}
        </div>

        {/* Recommendation */}
        {showRecommendation && (
          <div className="border-t pt-4">
            <div className="flex items-start gap-3">
              <TrendingUp className="h-5 w-5 text-green-600 mt-0.5" />
              <div className="flex-1 space-y-2">
                <div>
                  <div className="font-medium text-sm">Upgrade-Empfehlung verfügbar</div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {recommendation.reason}
                  </div>
                </div>
                {recommendation.upgrade_requirements.length > 0 && (
                  <div className="text-xs">
                    <div className="font-medium mb-1">Anforderungen:</div>
                    <ul className="list-disc list-inside space-y-0.5 text-muted-foreground">
                      {recommendation.upgrade_requirements.map((req, idx) => (
                        <li key={idx}>{req}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <Button
                  size="sm"
                  onClick={handleApplyRecommendation}
                  disabled={updateTrustLevel.isPending}
                  className="mt-2"
                  aria-label={`Auf Stufe ${recommendation.recommended_level} upgraden`}
                >
                  Auf Stufe {recommendation.recommended_level} upgraden
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Manual Level Change */}
        <div className="border-t pt-4 space-y-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <AlertTriangle className="h-4 w-4" />
            <span>Manuelle Stufenanpassung (Admin)</span>
          </div>
          <div className="flex gap-2">
            <Select value={selectedLevel} onValueChange={handleLevelChange}>
              <SelectTrigger className="flex-1" aria-label="Vertrauensstufe wählen">
                <SelectValue placeholder="Stufe wählen..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">Stufe 1: Assistenzmodus</SelectItem>
                <SelectItem value="2">Stufe 2: Auto-Akzeptanz</SelectItem>
                <SelectItem value="3">Stufe 3: Konfidenz-basiert</SelectItem>
                <SelectItem value="4">Stufe 4: Autonom</SelectItem>
              </SelectContent>
            </Select>
            <Button
              onClick={handleApplyLevel}
              disabled={!selectedLevel || updateTrustLevel.isPending}
              aria-label="Vertrauensstufe anwenden"
            >
              Anwenden
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
