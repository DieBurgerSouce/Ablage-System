/**
 * QualityScoreCard Component
 *
 * Zeigt die Qualitaetsbewertung eines einzelnen Dokuments:
 * - Grosses Ampel-Badge mit Score
 * - 3 Dimensionen als Fortschrittsbalken
 * - Empfehlungsliste
 */

import { cn } from '@/lib/utils';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { AmpelBadge } from './AmpelBadge';
import { formatScorePercent } from '../hooks/useDocumentQuality';
import type { DocumentQualityResponse } from '../types/quality-types';

// =============================================================================
// Dimension Bar Color
// =============================================================================

function getDimensionBarClass(score: number): string {
  if (score >= 0.8) return 'bg-green-500';
  if (score >= 0.5) return 'bg-yellow-500';
  return 'bg-red-500';
}

/** Gewichtung als Prozent-String */
function formatWeight(weight: number): string {
  return `${Math.round(weight * 100)} %`;
}

// =============================================================================
// Props
// =============================================================================

interface QualityScoreCardProps {
  /** Qualitaetsbewertung des Dokuments */
  quality: DocumentQualityResponse;
  /** Zusaetzliche CSS-Klassen */
  className?: string;
}

// =============================================================================
// Component
// =============================================================================

export function QualityScoreCard({ quality, className }: QualityScoreCardProps) {
  return (
    <Card className={cn('w-full', className)}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Datenqualitaet</CardTitle>
            <CardDescription>{quality.ampel_label}</CardDescription>
          </div>
          <AmpelBadge
            color={quality.ampel_color}
            score={quality.score}
            size="lg"
          />
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Dimensionen */}
        <div className="space-y-4">
          <h4 className="text-sm font-medium text-muted-foreground">
            Qualitaetsdimensionen
          </h4>
          {quality.dimensions.map((dimension) => (
            <div key={dimension.name} className="space-y-1.5">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{dimension.name}</span>
                <span className="text-muted-foreground">
                  {formatScorePercent(dimension.score)}
                  <span className="ml-1.5 text-xs">
                    (Gewicht: {formatWeight(dimension.weight)})
                  </span>
                </span>
              </div>
              <Progress
                value={dimension.score * 100}
                className="h-2"
                indicatorClassName={getDimensionBarClass(dimension.score)}
                aria-label={`${dimension.name}: ${formatScorePercent(dimension.score)}`}
              />
              <p className="text-xs text-muted-foreground">
                {dimension.details}
              </p>
            </div>
          ))}
        </div>

        {/* Empfehlungen */}
        {quality.recommendations.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-muted-foreground">
              Empfehlungen
            </h4>
            <ul className="space-y-1">
              {quality.recommendations.map((recommendation, index) => (
                <li
                  key={index}
                  className="flex items-start gap-2 text-sm text-muted-foreground"
                >
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground" />
                  {recommendation}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
