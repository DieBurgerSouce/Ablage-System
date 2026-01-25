/**
 * Risk Alert Banner Component
 *
 * Warnung-Banner fuer Hoch-Risiko Entities.
 * Wird auf Entity-Detail-Seiten angezeigt.
 */

import { AlertTriangle, X, TrendingUp, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { RiskScoreBadge } from './RiskScoreGauge';
import type { EntityRisk, RiskLevel } from '../types/risk-types';
import { RISK_LEVEL_LABELS, RISK_LEVEL_COLORS } from '../types/risk-types';

interface RiskAlertBannerProps {
  entityRisk: EntityRisk;
  showDismiss?: boolean;
  onDismiss?: () => void;
  compact?: boolean;
  className?: string;
}

export function RiskAlertBanner({
  entityRisk,
  showDismiss = false,
  onDismiss,
  compact = false,
  className,
}: RiskAlertBannerProps) {
  const { riskScore, riskLevel, riskFactors, entityName } = entityRisk;

  // Only show for high and critical risk
  if (riskLevel !== 'high' && riskLevel !== 'critical') {
    return null;
  }

  const colors = RISK_LEVEL_COLORS[riskLevel];

  // Find top risk factor
  const topFactor = riskFactors.reduce((max, factor) =>
    factor.contribution > max.contribution ? factor : max
  );

  const messages = getRiskMessages(riskLevel, topFactor.name);

  if (compact) {
    return (
      <div
        className={cn(
          'flex items-center gap-3 p-3 rounded-lg border-l-4',
          colors.bg,
          colors.border,
          className
        )}
      >
        <AlertTriangle className={cn('h-5 w-5 flex-shrink-0', colors.text)} />
        <div className="flex-1 min-w-0">
          <p className={cn('text-sm font-medium', colors.text)}>
            {messages.title}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Risiko-Score: {riskScore.toFixed(1)}
          </p>
        </div>
        {showDismiss && onDismiss && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 flex-shrink-0"
            onClick={onDismiss}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
    );
  }

  return (
    <Alert
      className={cn('border-l-4', colors.bg, colors.border, className)}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 flex-1">
          <AlertTriangle className={cn('h-5 w-5 mt-0.5', colors.text)} />
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <AlertTitle className={cn('mb-0', colors.text)}>
                {messages.title}
              </AlertTitle>
              <RiskScoreBadge score={riskScore} size="sm" />
            </div>
            <AlertDescription className="space-y-2">
              <p>{messages.description}</p>

              {/* Top Risk Factor */}
              <div className="flex items-center gap-2 text-sm">
                <TrendingUp className="h-4 w-4" />
                <span>
                  Hauptfaktor: <strong>{getFactorLabel(topFactor.name)}</strong>{' '}
                  (+{topFactor.contribution.toFixed(1)} Punkte)
                </span>
              </div>

              {/* Recommendations */}
              <div className="mt-3 p-3 rounded-lg bg-muted/50">
                <div className="flex items-start gap-2">
                  <Info className="h-4 w-4 mt-0.5 text-muted-foreground" />
                  <div className="text-sm">
                    <p className="font-medium mb-1">Empfohlene Maßnahmen:</p>
                    <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                      {messages.recommendations.map((rec, idx) => (
                        <li key={idx}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </AlertDescription>
          </div>
        </div>

        {showDismiss && onDismiss && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 flex-shrink-0"
            onClick={onDismiss}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
    </Alert>
  );
}

/**
 * Mini Risk Alert Badge (for inline warnings)
 */
interface RiskAlertBadgeProps {
  riskLevel: RiskLevel;
  score: number;
  className?: string;
}

export function RiskAlertBadge({
  riskLevel,
  score,
  className,
}: RiskAlertBadgeProps) {
  if (riskLevel !== 'high' && riskLevel !== 'critical') {
    return null;
  }

  const colors = RISK_LEVEL_COLORS[riskLevel];

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant="outline"
            className={cn(
              'gap-1 cursor-help',
              colors.bg,
              colors.text,
              colors.border,
              className
            )}
          >
            <AlertTriangle className="h-3 w-3" />
            <span>{RISK_LEVEL_LABELS[riskLevel]}</span>
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <p className="font-medium">Risiko-Score: {score.toFixed(1)}</p>
          <p className="text-xs text-muted-foreground mt-1">
            {riskLevel === 'critical'
              ? 'Sofortige Maßnahmen erforderlich'
              : 'Erhöhte Aufmerksamkeit empfohlen'}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/**
 * Risk Messages Helper
 */
function getRiskMessages(
  level: RiskLevel,
  topFactor: string
): {
  title: string;
  description: string;
  recommendations: string[];
} {
  if (level === 'critical') {
    return {
      title: 'Kritisches Risiko erkannt',
      description:
        'Dieser Geschäftspartner weist ein sehr hohes Risiko auf. Sofortige Maßnahmen werden empfohlen.',
      recommendations: getRecommendations(topFactor, true),
    };
  }

  return {
    title: 'Erhöhtes Risiko festgestellt',
    description:
      'Dieser Geschäftspartner sollte genauer überwacht werden. Präventive Maßnahmen könnten hilfreich sein.',
    recommendations: getRecommendations(topFactor, false),
  };
}

/**
 * Factor-specific recommendations
 */
function getRecommendations(
  factor: string,
  critical: boolean
): string[] {
  const baseRecs: Record<string, string[]> = {
    payment_delay: critical
      ? [
          'Kreditlimit überprüfen und ggf. reduzieren',
          'Zahlungsziel verkürzen',
          'Vorkasse oder Anzahlung verlangen',
        ]
      : [
          'Zahlungserinnerungen früher versenden',
          'Zahlungskonditionen überprüfen',
          'Persönlichen Kontakt aufnehmen',
        ],
    default_rate: critical
      ? [
          'Lieferstopp bis zur Begleichung offener Posten',
          'Inkasso beauftragen',
          'Sicherheiten einfordern',
        ]
      : [
          'Offene Posten klären',
          'Ratenzahlung anbieten',
          'Mahnstufe erhöhen',
        ],
    invoice_volume: critical
      ? [
          'Geschäftsbeziehung hinterfragen',
          'Mindestabnahmemenge vereinbaren',
          'Alternative Geschäftspartner prüfen',
        ]
      : [
          'Umsatzpotenzial analysieren',
          'Cross-Selling-Möglichkeiten prüfen',
          'Kundenbindungsmaßnahmen ergreifen',
        ],
    document_frequency: critical
      ? [
          'Regelmäßigen Kontakt etablieren',
          'Vertragskonditionen überprüfen',
          'Geschäftsbeziehung evaluieren',
        ]
      : [
          'Nachbestellungen anregen',
          'Serviceangebot verbessern',
          'Kundenzufriedenheit prüfen',
        ],
    relationship_age: critical
      ? [
          'Bonität umfassend prüfen',
          'Referenzen einholen',
          'Sicherheiten verlangen',
        ]
      : [
          'Engeren Kontakt pflegen',
          'Vertrauensbasis aufbauen',
          'Regelmäßige Bonitätsprüfung',
        ],
  };

  return baseRecs[factor] || [
    'Risikofaktoren regelmäßig überwachen',
    'Geschäftsbeziehung evaluieren',
    'Bei Bedarf Maßnahmen ergreifen',
  ];
}

/**
 * Factor Label Helper
 */
function getFactorLabel(factor: string): string {
  const labels: Record<string, string> = {
    payment_delay: 'Zahlungsverzögerung',
    default_rate: 'Ausfallrate',
    invoice_volume: 'Rechnungsvolumen',
    document_frequency: 'Dokumenthäufigkeit',
    relationship_age: 'Beziehungsdauer',
  };
  return labels[factor] || factor;
}
